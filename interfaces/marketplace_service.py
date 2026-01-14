# marketplace_service.py

from abc import ABC, abstractmethod
from typing import Optional

from models.standard_models import StandardCurrentOffer, CompetitionResult


class IMarketplaceService(ABC):

    @abstractmethod
    async def get_my_offer_details(self, offer_id: str) -> Optional[StandardCurrentOffer]:
        """Lấy thông tin offer hiện tại của mình và chuẩn hóa về StandardCurrentOffer"""
        pass

    @abstractmethod
    async def get_competitor_prices(
            self,
            product_compare: str,
            min_price: Optional[float] = None,
            max_price: Optional[float] = None
    ) -> CompetitionResult:
        """Lấy danh sách giá đối thủ và chuẩn hóa về CompetitionResult"""
        pass

    @abstractmethod
    async def update_price(self, offer_id: str, new_price: float, offer_type: str) -> bool:
        """Cập nhật giá"""
        pass
