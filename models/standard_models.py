# standard_models.py

from typing import List, Optional

from pydantic import BaseModel


class StandardCompetitorOffer(BaseModel):
    price: float
    seller_name: str
    rating: int = 0
    is_eligible: bool = True
    note: Optional[str] = None


class StandardCurrentOffer(BaseModel):
    offer_id: str
    price: float
    status: str
    offer_type: str  # Ví dụ: 'dropshipping', 'key', 'gift'
    currency: str = "EUR"


class CompetitionResult(BaseModel):
    offers: List[StandardCompetitorOffer]
