import logging
from typing import Any, Dict

from clients.base_rest_client import BaseRestAPIClient
from logic.auth import AuthHandler
from models.driffle_models import OffersResponse, ProductsResponse, UpdateOfferResponse, ProductCompetitionsResponse
from utils.config import settings


class DriffleClient(BaseRestAPIClient):
    def __init__(self, auth_handler: AuthHandler):
        super().__init__(base_url=settings.BASE_URL)
        self.auth_handler = auth_handler

    async def _prepare_payload(self, auth_required: bool, **kwargs: Any) -> Dict[str, Any]:
        if auth_required:
            auth_headers = await self.auth_handler.get_auth_headers()
            self._client.headers.update(auth_headers)
        return kwargs

    async def get_offers_by_pid(self, pid: int) -> OffersResponse:
        return await self.get(
            endpoint="offers",
            response_model=OffersResponse,
            auth_required=True,
            pid=pid
        )

    async def get_products(self) -> ProductsResponse:
        return await self.get(
            endpoint="products",
            response_model=ProductsResponse,
            auth_required=True
        )

    async def update_offer(self, offer_id: int, new_price: float, active: bool = True) -> UpdateOfferResponse:
        toggle_status = "enable" if active else "disable"
        logging.info("Updating offer %s: new price=%s, status=%s", offer_id, new_price, toggle_status)
        return await self.patch(
            endpoint="offer/update",
            response_model=UpdateOfferResponse,
            auth_required=True,
            offerId=offer_id,
            yourPrice=new_price,
            toggleOffer=toggle_status
        )

    async def get_product_competitions(self, pid: int) -> ProductCompetitionsResponse:
        return await self.get(
            endpoint=f"products/{pid}/competitions",
            response_model=ProductCompetitionsResponse,
            auth_required=True
        )

    async def close(self):
        await super().close()
        if self.auth_handler:
            await self.auth_handler.close()
