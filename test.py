import logging

import pytest

from clients.driffle_client import DriffleClient
from logic.auth import AuthHandler

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_driffle_get_offers():
    auth_handler = AuthHandler()
    driffle_client = DriffleClient(auth_handler=auth_handler)

    async with driffle_client:
        try:
            product_id = 62593
            logger.info(f"--- Testing Driffle API for PID: {product_id} ---")

            response = await driffle_client.get_pid_by_offer_id(pid=product_id)

            logger.info(f"Status: {response.statusCode} | Message: {response.message}")

            if response.data:
                logger.info(f"Total Offers Found: {len(response.data)}")
                for offer in response.data:
                    logger.info(
                        f"> Offer {offer.offerId} | "
                        f"Price: {offer.sellingPrice.amount} {offer.sellingPrice.currency} | "
                        f"Stock: {offer.onHand} | "
                        f"Lowest: {offer.isLowest}"
                    )
            else:
                logger.warning("No data returned.")

        except Exception as e:
            # logger.error với exc_info=True sẽ in luôn cả Stack Trace lỗi
            logger.error(f"An error occurred: {e}", exc_info=True)


@pytest.mark.asyncio
async def test_driffle_get_products():
    auth_handler = AuthHandler()
    driffle_client = DriffleClient(auth_handler=auth_handler)

    async with driffle_client:
        try:
            logger.info("\n--- Testing Get All Products ---")

            # Gọi API lấy sản phẩm
            response = await driffle_client.get_products()

            logger.info(f"Status: {response.statusCode} | Message: {response.message}")

            if response.data:
                total_products = len(response.data)
                logger.info(f"Total Products Retrieved: {total_products}")

                # In thử 3 sản phẩm đầu tiên để kiểm tra
                for i, prod in enumerate(response.data[:3]):
                    logger.info(
                        f"#{i + 1} [ID: {prod.productId}] {prod.title} | "
                        f"Region: {prod.regionName} | "
                        f"Price Range: {prod.minPrice}-{prod.maxPrice}"
                    )
            else:
                logger.warning("No products found in the response.")

        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    asyncio.run(test_driffle_get_offers())
