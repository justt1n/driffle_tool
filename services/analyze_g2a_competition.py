import logging
from typing import List

from models.logic_models import AnalysisResult
from models.sheet_models import Payload
from models.standard_models import StandardCompetitorOffer

logger = logging.getLogger(__name__)


class CompetitionAnalysisService:

    def analyze_competition(self, payload: Payload, offers: List[StandardCompetitorOffer]) -> AnalysisResult:
        blacklist = payload.fetched_black_list or []

        filtered_offers = [
            offer for offer in offers
            if offer.seller_name.lower() not in (seller.lower() for seller in blacklist)
        ]

        if not filtered_offers:
            logger.warning(f"No valid offers found for {payload.product_name} after filtering blacklist.")
            return AnalysisResult(
                competitor_name=None,
                competitive_price=None,
                top_sellers_for_log=offers,
                sellers_below_min=[]
            )

        lowest_offer = min(filtered_offers, key=lambda offer: offer.price)

        min_price_val = payload.get_min_price_value()
        sellers_below_min = []
        if min_price_val is not None:
            sellers_below_min = [
                offer for offer in offers
                if offer.price < min_price_val
            ]

        return AnalysisResult(
            competitor_name=lowest_offer.seller_name,
            competitive_price=lowest_offer.price,
            top_sellers_for_log=offers,
            sellers_below_min=sellers_below_min
        )
