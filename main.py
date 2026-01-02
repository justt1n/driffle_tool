import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from clients.driffle_client import DriffleClient
from clients.google_sheets_client import GoogleSheetsClient
from interfaces.marketplace_service import IMarketplaceService
from logic.auth import AuthHandler
from logic.universal_processor import UniversalProcessor
from services.analyze_g2a_competition import CompetitionAnalysisService
from services.driffle_adapter import DriffleServiceAdapter, extract_pid
from services.sheet_service import SheetService
from utils.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

CONCURRENT_WORKERS = getattr(settings, 'WORKERS', 1)


def _detect_platform(payload) -> str:
    """
    Vì đã bỏ G2A, mặc định mọi dòng đều được coi là Driffle.
    Bạn có thể thêm logic check URL nếu muốn strict hơn.
    """
    return "driffle"


async def process_row_wrapper(
        payload,
        sheet_service: SheetService,
        processors: Dict[str, UniversalProcessor],
        adapters: Dict[str, IMarketplaceService],
        worker_semaphore: asyncio.Semaphore,
        google_sheets_lock: asyncio.Semaphore,
        client: DriffleClient
) -> Optional[Tuple[Any, Dict[str, Any]]]:
    """
    Worker xử lý 1 hàng.
    """
    try:
        # 1. Xác định nền tảng (Mặc định trả về 'driffle')
        platform = _detect_platform(payload)

        processor = processors.get(platform)
        adapter = adapters.get(platform)

        if not processor or not adapter:
            logging.error(f"Unsupported platform '{platform}' or missing config.")
            return (payload, {'note': f"Error: Config missing for {platform}"})

        logging.info(f"Start processing row {payload.row_index} ({payload.product_name})...")

        # 2. Lấy dữ liệu từ Sheet
        async with google_sheets_lock:
            hydrated_payload = await asyncio.to_thread(
                sheet_service.fetch_data_for_payload, payload
            )

        # 3. Chạy Processor (Logic tính toán giá)
        ## fulfill payload ===
        service = DriffleServiceAdapter(client)
        _offer_id = extract_pid(str(hydrated_payload.product_id))
        hydrated_payload.real_offer_id = _offer_id
        payload.real_product_id = await service.get_pid_by_offer_id(str(_offer_id))
        ## ==============================
        result = await processor.process_single_payload(hydrated_payload)
        log_data = None

        # 4. Thực hiện Update
        if result.status == 1 and result.final_price is not None and result.offer_id:
            # Gọi API Update của Driffle
            update_successful = await adapter.update_price(
                offer_id=result.offer_id,
                offer_type=result.offer_type or "key",
                new_price=result.final_price.price
            )

            if update_successful:
                logging.info(f"SUCCESS: Updated {payload.product_name} -> {result.final_price.price:.3f}")
                log_data = {
                    'note': result.log_message,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                logging.error(f"FAILED API Update: {payload.product_name}")
                log_data = {
                    'note': f"{result.log_message}\n\nERROR: API update call failed.",
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        else:
            # Logic skip (status 0 hoặc 2)
            log_data = {
                'note': result.log_message,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        # 5. Logic Relax
        if payload.relax:
            try:
                sleep_time = int(payload.relax)
                if sleep_time > 0:
                    logging.info(f"Row {payload.row_index} relaxing for {sleep_time}s...")
                    await asyncio.sleep(sleep_time)
            except (ValueError, TypeError):
                pass

        if log_data:
            return (payload, log_data)
        return None

    except Exception as e:
        logging.error(f"Error processing row {payload.row_index}: {e}", exc_info=True)
        return (payload, {'note': f"Error: {e}"})

    finally:
        worker_semaphore.release()


async def run_automation(
        sheet_service: SheetService,
        processors: Dict[str, UniversalProcessor],
        adapters: Dict[str, IMarketplaceService],
        google_sheets_lock: asyncio.Semaphore,
        client: DriffleClient
):
    worker_semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
    batch_size = CONCURRENT_WORKERS

    try:
        logging.info("Fetching payloads from Google Sheets...")

        all_payloads = await asyncio.to_thread(
            sheet_service.get_payloads_to_process
        )

        if not all_payloads:
            logging.info("No payloads to process.")
            return

        total_payloads = len(all_payloads)
        logging.info(f"Found {total_payloads} payloads. Processing with {CONCURRENT_WORKERS} workers...")

        for i in range(0, total_payloads, batch_size):
            batch_payloads = all_payloads[i: i + batch_size]
            current_batch_num = (i // batch_size) + 1

            logging.info(f"--- Batch {current_batch_num} ---")

            tasks = []
            for payload in batch_payloads:
                await worker_semaphore.acquire()
                task = asyncio.create_task(
                    process_row_wrapper(
                        payload=payload,
                        sheet_service=sheet_service,
                        processors=processors,
                        adapters=adapters,
                        worker_semaphore=worker_semaphore,
                        google_sheets_lock=google_sheets_lock,
                        client=client
                    )
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            updates_to_push = [res for res in results if res is not None]

            if updates_to_push:
                logging.info(f"Batch {current_batch_num} done. Updating Sheet logs...")
                await asyncio.to_thread(
                    sheet_service.batch_update_logs, updates_to_push
                )
            else:
                logging.info(f"Batch {current_batch_num} done. Nothing to log.")

        logging.info("All batches processed successfully.")

    except Exception as e:
        logging.critical(f"Error in run_automation: {e}", exc_info=True)


async def main():
    google_sheets_lock = asyncio.Semaphore(1)

    driffle_client = None

    try:
        logging.info("Initializing services...")

        # 1. Google Sheets Service
        g_client = GoogleSheetsClient(settings.GOOGLE_KEY_PATH)
        sheet_service = SheetService(client=g_client)

        # 2. Analysis Service (Logic phân tích giá)
        analysis_service = CompetitionAnalysisService()

        driffle_key = settings.AUTH_SECRET

        if not driffle_key:
            logging.warning("Warning: DRIFFLE_API_KEY is missing in settings!")

        # Khởi tạo Client -> Adapter -> Processor
        driffle_client = DriffleClient(AuthHandler())
        driffle_adapter = DriffleServiceAdapter(driffle_client)
        driffle_processor = UniversalProcessor(
            market_service=driffle_adapter,
            analysis_service=analysis_service
        )

        # ==========================================
        # MAP SERVICES
        # ==========================================
        # Chỉ đăng ký service driffle
        processors_map = {
            "driffle": driffle_processor
        }

        adapters_map = {
            "driffle": driffle_adapter
        }

        logging.info("Services ready. Platform: Driffle")

        while True:
            try:
                logging.info("===== NEW ROUND =====")

                await run_automation(
                    sheet_service=sheet_service,
                    processors=processors_map,
                    adapters=adapters_map,
                    google_sheets_lock=google_sheets_lock,
                    client=driffle_client
                )

                logging.info(f"Round finished. Sleep {settings.SLEEP_TIME}s.")
                await asyncio.sleep(settings.SLEEP_TIME)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.critical(f"Error in main loop: {e}. Retry in 30s.", exc_info=True)
                await asyncio.sleep(30)

    finally:
        logging.info("Shutting down...")
        if driffle_client and hasattr(driffle_client, 'close'):
            await driffle_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
