import asyncio
import logging
from typing import Optional, Dict

from clients.driffle_client import DriffleClient
from interfaces.marketplace_service import IMarketplaceService
from models.driffle_models import SingleOfferResponse
from models.standard_models import StandardCurrentOffer, StandardCompetitorOffer, CompetitionResult

logger = logging.getLogger(__name__)


def extract_pid(product_identifier: str) -> Optional[int]:
    """
    Extracts the product ID (PID) from the given product identifier URL.
    Example: https://driffle.com/vi/user/selling/currently-selling/700583 -> 700583
    """
    try:
        # Validate and extract the last part of the URL
        parts = product_identifier.rstrip("/").split("/")
        if not parts or not parts[-1].isdigit():
            logger.warning(f"Invalid product identifier format: {product_identifier}")
            return None

        return int(parts[-1])
    except Exception as e:
        logger.error(f"Error extracting PID from product identifier: {product_identifier}, {e}")
        return None


class DriffleServiceAdapter(IMarketplaceService):
    def __init__(self, client: DriffleClient):
        self.client = client

    async def get_my_offer_details(self, offer_id: str) -> Optional[StandardCurrentOffer]:
        """
        Lấy thông tin offer hiện tại của mình.
        Mapping:
        - Driffle 'offerId' -> Standard 'offer_id'
        - Driffle 'sellingPrice.amount' (str) -> Standard 'price' (float)
        """
        try:
            response = await self.client.get_offer_details(int(offer_id))

            if not response or not response.data or not response.data.offer:
                logger.warning(f"Offer ID {offer_id} not found/fetch failed.")
                return None

            offer_data = response.data.offer

            current_base_price = offer_data.price.yourPrice

            return StandardCurrentOffer(
                offer_id=str(offer_data.offerId),
                price=current_base_price,
                status=str(offer_data.status),  # 1: Active
                offer_type="key",
                currency="EUR"
            )

        except Exception as e:
            logger.error(f"Error getting my offer details for {offer_id}: {e}", exc_info=True)
            return None

    async def get_competitor_prices(
            self,
            product_compare: str,
            min_price: Optional[float] = None,
            max_price: Optional[float] = None
    ) -> CompetitionResult:
        try:
            pid = int(product_compare)
            if not pid:
                return CompetitionResult(offers=[])

            response = await self.client.get_product_competitions(pid=pid)
            if not response or not response.competitions or not response.competitions.offers:
                return CompetitionResult(offers=[])

            limit_min_base = min_price if min_price is not None else 0.0
            limit_max_base = max_price if max_price is not None else float('inf')

            # Danh sách để tính toán commission (chỉ tính cho những thằng CÓ THỂ hợp lệ)
            potential_retail_prices = set()

            # Danh sách kết quả tạm
            all_offers_raw = []

            for item in response.competitions.offers:
                if item.belongsToYou or not item.isInStock or not item.canBePurchased:
                    continue

                retail_val = item.price.amount

                # Check 1: Pre-filter (Retail < Min Base)
                # Nếu Retail đã thấp hơn Min Base -> Chắc chắn Base thấp hơn -> Loại luôn, khỏi tính Com.
                if retail_val < limit_min_base:
                    # Thêm vào list nhưng đánh dấu FALSE
                    all_offers_raw.append({
                        "item": item,
                        "base_price": retail_val,  # Lưu tạm retail để log
                        "is_eligible": False,
                        "note": f"Retail({retail_val}) < Min({limit_min_base})"
                    })
                    continue

                # Nếu qua vòng gửi xe, thêm vào danh sách cần tính Commission
                potential_retail_prices.add(retail_val)
                all_offers_raw.append({
                    "item": item,
                    "base_price": None,  # Chờ tính
                    "is_eligible": True,  # Tạm thời True
                    "note": None
                })

            # Tính toán Commission cho các Unique Retail Price
            sorted_retail_prices = sorted(list(potential_retail_prices))[:8]
            price_map: Dict[float, float] = {}

            for retail_price in sorted_retail_prices:
                try:
                    res = await self.client.calculate_commission(product_id=pid, selling_price=retail_price)
                    if res and res.data and res.data.youGetPrice:
                        price_map[retail_price] = res.data.youGetPrice.amount
                    else:
                        price_map[retail_price] = round(retail_price * 0.88, 2)
                except Exception:
                    price_map[retail_price] = round(retail_price * 0.88, 2)
                await asyncio.sleep(0.3)

            # Build kết quả cuối cùng
            standard_offers = []

            for entry in all_offers_raw:
                item = entry["item"]

                # Nếu đã bị loại ở vòng 1 (Retail < Min)
                if not entry["is_eligible"]:
                    standard_offers.append(StandardCompetitorOffer(
                        seller_name=item.merchantName,
                        price=entry["base_price"],
                        is_eligible=False,
                        note=entry["note"]
                    ))
                    continue

                # Xử lý những thằng vào vòng 2
                retail = item.price.amount
                if retail in price_map:
                    real_base_price = price_map[retail]

                    # CHECK RANGE CHÍNH THỨC (Base vs Min/Max)
                    if limit_min_base <= real_base_price <= limit_max_base:
                        standard_offers.append(StandardCompetitorOffer(
                            seller_name=item.merchantName,
                            price=real_base_price,
                            is_eligible=True  # Hợp lệ
                        ))
                    else:
                        # Bị loại ở vòng 2
                        note = "Base < Min" if real_base_price < limit_min_base else "Base > Max"
                        standard_offers.append(StandardCompetitorOffer(
                            seller_name=item.merchantName,
                            price=real_base_price,
                            is_eligible=False,  # Loại
                            note=f"{note} ({real_base_price})"
                        ))
                else:
                    # Trường hợp không nằm trong top ưu tiên tính toán -> Coi như loại hoặc ignore
                    pass

            return CompetitionResult(offers=standard_offers)

        except Exception as e:
            logger.error(f"Error getting competition: {e}", exc_info=True)
            return CompetitionResult(offers=[])

    async def update_price(self, offer_id: str, new_price: float, offer_type: str) -> bool:
        """
        Cập nhật giá mới lên Driffle.
        """
        try:
            # offer_id bên Standard là str, bên Driffle update cần int
            oid = int(offer_id)

            response = await self.client.update_offer(
                offer_id=oid,
                new_price=new_price,
                active=True  # Mặc định update giá là enable luôn
            )

            if response and response.statusCode == 200:
                logger.info(f"Successfully updated Driffle offer {offer_id} to {new_price}")
                return True
            else:
                msg = response.message if response else "Unknown error"
                logger.error(f"Failed to update Driffle offer {offer_id}: {msg}")
                return False

        except Exception as e:
            logger.error(f"Exception updating price for {offer_id}: {e}")
            return False

    async def get_pid_by_offer_id(self, product_id: str) -> str:
        try:
            pid_int = int(product_id)

            response: SingleOfferResponse = await self.client.get_offer_details(offer_id=pid_int)

            if not response.data:
                msg = f"No offers found for product_id: {product_id}"
                logger.warning(msg)
                raise ValueError(msg)

            return str(response.data.offer.productId)

        except ValueError as e:
            logger.error(f"Error getting offer_id for product {product_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in get_offer_id_by_product_id: {e}")
            raise
