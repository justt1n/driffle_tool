import logging
import random
from typing import Optional

from interfaces.marketplace_service import IMarketplaceService
from models.logic_models import PayloadResult, CompareTarget
from models.sheet_models import Payload
from services.analyze_g2a_competition import CompetitionAnalysisService
from utils.g2a_logger import get_g2a_log_string
from utils.utils import round_up_to_n_decimals

logger = logging.getLogger(__name__)


class UniversalProcessor:
    def __init__(self, market_service: IMarketplaceService, analysis_service: CompetitionAnalysisService):
        self.market_service = market_service
        self.analysis_service = analysis_service

    def _calc_final_price(self, payload: Payload, price: Optional[float]) -> float:
        # Reset giá trị điều chỉnh mỗi lần tính toán lại
        payload.applied_adj = 0.0

        if price is None:
            price = payload.fetched_max_price if payload.fetched_max_price is not None else float('inf')

        if price == float('inf'):
            return payload.fetched_max_price

        # --- TÍNH TOÁN RANDOM VÀ LƯU VÀO PAYLOAD ---
        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            min_adj = min(payload.min_price_adjustment, payload.max_price_adjustment)
            max_adj = max(payload.min_price_adjustment, payload.max_price_adjustment)

            # Tính số random
            d_price = random.uniform(min_adj, max_adj)

            # LƯU VÀO PAYLOAD ĐỂ DÙNG LẠI HOẶC LOG
            payload.applied_adj = d_price

            # Trừ giá
            price -= d_price

        if payload.fetched_min_price is not None:
            price = max(price, payload.fetched_min_price)

        if payload.fetched_max_price is not None:
            price = min(price, payload.fetched_max_price)

        if payload.price_rounding is not None:
            price = round_up_to_n_decimals(price, payload.price_rounding)

        return price

    def _validate_payload(self, payload: Payload) -> bool:
        # (Giữ nguyên)
        if not payload.product_name:
            logger.warning("Payload validation failed: product_name is required.")
            return False
        if payload.price_rounding is not None and payload.price_rounding < 0:
            logger.warning("Payload validation failed: price_rounding cannot be negative.")
            return False
        if payload.product_compare is None:
            logger.warning("Payload validation failed: product_compare is required for comparison.")
            return False
        return True

    def _is_price_diff_significant(self, price1: float, price2: float, payload: Payload) -> bool:
        """
        True = CẦN Update (Lệch lớn).
        False = KHÔNG Update (Lệch nhỏ do random/làm tròn).
        """
        step = 0.01
        if payload.price_rounding is not None:
            step = 1 / (10 ** payload.price_rounding)

        random_noise = 0.0
        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            random_noise = abs(payload.max_price_adjustment - payload.min_price_adjustment)

        # Ngưỡng = Biên độ dao động Random + Sai số làm tròn
        threshold = random_noise + (step * 0.5)
        threshold = max(threshold, step * 1.5)  # Tối thiểu chặn được sai số 1 đơn vị

        return abs(price1 - price2) > threshold

    async def process_single_payload(self, payload: Payload) -> PayloadResult:
        """
        Phiên bản khớp với Interface:
        - get_my_offer_details
        - get_competitor_prices -> trả về CompetitionResult
        """
        # 0. Validate Payload
        if not self._validate_payload(payload):
            return PayloadResult(status=0, payload=payload, log_message="Payload validation failed.")

        try:
            # =========================================================================
            # BƯỚC 1: LẤY THÔNG TIN HÀNG CỦA MÌNH (OWN OFFER)
            # =========================================================================

            # Lưu ý: Payload thường chứa URL hoặc ID thô trong field product_id.
            # Adapter (lớp hiện thực Interface) phải tự xử lý việc parse nếu cần,
            # hoặc bạn phải parse trước khi truyền vào đây.
            # Ở đây tôi truyền thẳng payload.product_id vào.
            current_offer = await self.market_service.get_my_offer_details(payload.product_compare)

            if not current_offer:
                return PayloadResult(
                    status=0,
                    payload=payload,
                    log_message=f"Fetch Current Details Failed for {payload.product_id}"
                )

            # Map dữ liệu chuẩn từ StandardCurrentOffer vào Payload
            payload.current_price = current_offer.price
            payload.offer_id = current_offer.offer_id
            offer_type = current_offer.offer_type

            mode = payload.get_compare_mode

            # =========================================================================
            # MODE 0: NOT COMPARE
            # =========================================================================
            if mode == 0:
                logger.info(f"Mode 0: Not Compare {payload.product_name}")
                if payload.fetched_min_price is None:
                    return PayloadResult(status=0, payload=payload, log_message="Mode 0: No Min Price")

                final_price = round_up_to_n_decimals(payload.fetched_min_price, payload.price_rounding)
                payload.applied_adj = 0.0

                if not self._is_price_diff_significant(payload.current_price, final_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=payload.offer_id)

                log_str = get_g2a_log_string("not_compare", payload, final_price)
                return PayloadResult(
                    status=1,
                    payload=payload,
                    final_price=CompareTarget(name="No Comparison", price=final_price),
                    log_message=log_str,
                    offer_id=payload.offer_id,
                    offer_type=offer_type
                )

            # =========================================================================
            # BƯỚC 2: LẤY DỮ LIỆU ĐỐI THỦ (COMPETITION)
            # =========================================================================

            # Gọi hàm get_competitor_prices theo đúng Interface
            comp_result = await self.market_service.get_competitor_prices(payload.product_compare)

            # Trích xuất list offers từ object CompetitionResult
            competitor_offers = comp_result.offers

            # Tính toán giá mục tiêu
            if not competitor_offers:
                logger.warning(f"No competition found for {payload.product_name}")
                target_price = self._calc_final_price(payload, None)
                competitor_name = "No Competition"
                analysis_result = None
            else:
                # Analysis service cần nhận List[StandardCompetitorOffer]
                analysis_result = self.analysis_service.analyze_competition(payload, competitor_offers)
                target_price = self._calc_final_price(payload, analysis_result.competitive_price)
                competitor_name = analysis_result.competitor_name

            # =========================================================================
            # BƯỚC 3: XỬ LÝ MIN PRICE PROTECTION
            # =========================================================================
            min_price_value = payload.get_min_price_value()

            if min_price_value is not None:
                if payload.current_price < min_price_value:
                    logger.info(f"Current ({payload.current_price}) < Min. Force update to Min.")
                    target_price = min_price_value
                    payload.applied_adj = 0.0
                elif target_price < min_price_value:
                    log_str = get_g2a_log_string("below_min", payload, target_price, analysis_result)
                    return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)
            elif min_price_value is None:
                log_str = get_g2a_log_string("no_min_price", payload, target_price, analysis_result)
                return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)

            # =========================================================================
            # MODE 1: LUÔN THEO SAU (Standard Follow)
            # =========================================================================
            if mode == 1:
                if not self._is_price_diff_significant(payload.current_price, target_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=payload.offer_id)

                log_str = get_g2a_log_string("compare", payload, target_price, analysis_result)
                return PayloadResult(
                    status=1,
                    payload=payload,
                    competition=competitor_offers,
                    final_price=CompareTarget(name=competitor_name, price=target_price),
                    log_message=log_str,
                    offer_id=payload.offer_id,
                    offer_type=offer_type
                )

            # =========================================================================
            # MODE 2: CHỈ GIẢM KHÔNG TĂNG (Smart/Lazy Follow)
            # =========================================================================
            elif mode == 2:
                # Check 1: Giữ giá tốt
                if payload.current_price < target_price and self._is_price_diff_significant(payload.current_price,
                                                                                            target_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    log_str = log_str.replace("đã khớp mục tiêu", "đang thấp hơn mục tiêu (Mode 2 - Giữ giá)")
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=payload.offer_id)

                # Check 2: Noise
                if not self._is_price_diff_significant(payload.current_price, target_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=payload.offer_id)

                # Case B: Undercut
                log_str = get_g2a_log_string("compare", payload, target_price, analysis_result)
                return PayloadResult(
                    status=1,
                    payload=payload,
                    competition=competitor_offers,
                    final_price=CompareTarget(name=competitor_name, price=target_price),
                    log_message=log_str,
                    offer_id=payload.offer_id,
                    offer_type=offer_type
                )

            return PayloadResult(status=0, payload=payload, log_message=f"Unknown Mode: {mode}")

        except Exception as e:
            logger.error(f"Error processing payload {payload.product_name}: {e}", exc_info=True)
            return PayloadResult(status=0, payload=payload, log_message=f"Error: {str(e)}", final_price=None)
