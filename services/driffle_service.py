import logging

from clients.driffle_client import DriffleClient
from models.driffle_models import OffersResponse

logger = logging.getLogger(__name__)


class DriffleService:
    def __init__(self, client: DriffleClient):
        self.client = client

    async def get_offer_id_by_product_id(self, product_id: str) -> str:
        try:
            pid_int = int(product_id)

            response: OffersResponse = await self.client.get_offers_by_pid(pid=pid_int)

            if not response.data:
                msg = f"No offers found for product_id: {product_id}"
                logger.warning(msg)
                raise ValueError(msg)

            first_offer = response.data[0]

            if first_offer.product.id != pid_int:
                logger.warning(f"Returned offer product ID {first_offer.product.id} does not match requested {pid_int}")

            return str(first_offer.offerId)

        except ValueError as e:
            logger.error(f"Error getting offer_id for product {product_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in get_offer_id_by_product_id: {e}")
            raise


