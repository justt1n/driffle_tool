import logging
import re
from typing import Optional

from clients.driffle_client import DriffleClient
from interfaces.marketplace_service import IMarketplaceService
from models.standard_models import StandardCurrentOffer, StandardCompetitorOffer, CompetitionResult

logger = logging.getLogger(__name__)


class DriffleServiceAdapter(IMarketplaceService):
    def __init__(self, client: DriffleClient):
        self.client = client

    def _extract_pid(self, product_identifier: str) -> Optional[int]:
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

    async def get_my_offer_details(self, offer_id: str) -> Optional[StandardCurrentOffer]:
        """
        Lấy thông tin offer hiện tại của mình.
        Mapping:
        - Driffle 'offerId' -> Standard 'offer_id'
        - Driffle 'sellingPrice.amount' (str) -> Standard 'price' (float)
        """
        try:
            response = await self.client.get_offers_by_pid(pid=offer_id)

            if not response or not response.data:
                logger.warning(f"No offer found in My Inventory for PID {offer_id}")
                return None

            # Giả định: Một PID ta chỉ bán 1 Offer. Lấy cái đầu tiên.
            my_item = response.data[0]

            # Convert price từ string sang float (Model OfferItem define amount là str)
            try:
                price_val = float(my_item.sellingPrice.amount)
            except (ValueError, TypeError):
                price_val = 0.0

            return StandardCurrentOffer(
                offer_id=str(my_item.offerId),
                price=price_val,
                status=str(my_item.status),  # 1: Active, etc.
                offer_type="key",  # Driffle chủ yếu bán Key
                currency=my_item.sellingPrice.currency
            )

        except Exception as e:
            logger.error(f"Error getting my offer details for {offer_id}: {e}", exc_info=True)
            return None

    async def get_competitor_prices(self, product_compare: str) -> CompetitionResult:
        """
        Lấy danh sách giá đối thủ.
        Sử dụng API Competitions của Driffle.
        """
        try:
            # product_compare trong sheet thường là URL đối thủ -> Extract PID
            pid = self._extract_pid(product_compare)
            if not pid:
                logger.warning(f"Could not extract PID from compare URL: {product_compare}")
                return CompetitionResult(offers=[])

            # Gọi API lấy đối thủ
            response = await self.client.get_product_competitions(pid=pid)

            if not response or not response.competitions or not response.competitions.offers:
                return CompetitionResult(offers=[])

            standard_offers = []

            for item in response.competitions.offers:
                # 1. Bỏ qua chính mình
                if item.belongsToYou:
                    continue

                # 2. Bỏ qua nếu không stock hoặc không mua được
                if not item.isInStock or not item.canBePurchased:
                    continue

                # 3. Mapping dữ liệu
                # Model CompetitionPrice define amount là float -> dùng luôn
                standard_offers.append(StandardCompetitorOffer(
                    seller_name=item.merchantName,
                    price=item.price.amount,
                    rating=0  # Driffle Competition API hiện chưa trả rating
                ))

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
