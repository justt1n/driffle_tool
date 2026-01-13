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

    async def get_competitor_prices(self, product_compare: str) -> CompetitionResult:
        try:
            pid = int(product_compare)
            if not pid:
                return CompetitionResult(offers=[])

            response = await self.client.get_product_competitions(pid=pid)

            if not response or not response.competitions or not response.competitions.offers:
                return CompetitionResult(offers=[])

            valid_offers = []
            for item in response.competitions.offers:
                if item.belongsToYou: continue
                if not item.isInStock or not item.canBePurchased: continue
                valid_offers.append(item)

            valid_offers.sort(key=lambda x: x.price.amount)

            if not valid_offers:
                return CompetitionResult(offers=[])

            unique_prices_to_calc = set()
            for offer in valid_offers:
                unique_prices_to_calc.add(offer.price.amount)
                if len(unique_prices_to_calc) >= 4:
                    break

            price_map: Dict[float, float] = {}

            tasks = []
            price_keys = list(unique_prices_to_calc)

            for retail_price in price_keys:
                tasks.append(self.client.calculate_commission(product_id=pid, selling_price=retail_price))

            results = await asyncio.gather(*tasks)

            for idx, res in enumerate(results):
                input_retail = price_keys[idx]
                if res and res.data and res.data.youGetPrice:
                    price_map[input_retail] = res.data.youGetPrice.amount
                else:
                    # Nếu lỗi API, fallback tạm dùng retail
                    logger.error("Cant get seller price")
                    price_map[input_retail] = input_retail

            standard_offers = []

            for item in valid_offers:
                retail_price = item.price.amount

                if retail_price in price_map:
                    base_price = price_map[retail_price]

                    standard_offers.append(StandardCompetitorOffer(
                        seller_name=item.merchantName,
                        price=base_price,  # ĐÂY LÀ BASE PRICE (You Get)
                        rating=0
                    ))
                # Có thể uncomment dòng dưới nếu muốn giữ cả các đối thủ giá cao (nhưng là giá Retail)
                # standard_offers.append(StandardCompetitorOffer(seller_name=item.merchantName, price=retail_price))

            return CompetitionResult(offers=standard_offers)

        except Exception as e:
            logger.error(f"Error getting competition for {product_compare}: {e}", exc_info=True)
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
