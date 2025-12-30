from typing import List, Optional

from pydantic import BaseModel

from models.sheet_models import Payload
from models.standard_models import StandardCompetitorOffer


class CompareTarget(BaseModel):
    name: str
    price: float


class AnalysisResult(BaseModel):
    competitor_name: str | None = None
    competitive_price: float | None = None
    top_sellers_for_log: Optional[List[StandardCompetitorOffer]] = None
    sellers_below_min: Optional[List[StandardCompetitorOffer]] = None


class PayloadResult(BaseModel):
    status: int  # 1 for success, 0 for failure
    payload: Payload
    competition: list[StandardCompetitorOffer] | None = None
    final_price: CompareTarget | None = None
    log_message: str | None = None

    offer_id: Optional[str] = None
    offer_type: Optional[str] = None
