from typing import List, Optional, Dict, Any

from pydantic import BaseModel


# --- Sub-models ---

class ProductInfo(BaseModel):
    id: int
    title: str
    productStatus: int
    isPreReleased: int


class Money(BaseModel):
    amount: str
    currency: str


class Commission(BaseModel):
    type: str
    amount: str
    currency: str


class AutomatePriceOptions(BaseModel):
    lowerPriceLimit: Optional[float] = None
    higherPriceLimit: Optional[float] = None
    priceChangeInterval: Optional[int] = None
    priceChangeFactor: Optional[float] = None
    automatePriceStatus: str


# --- Main Object Model ---

class OfferItem(BaseModel):
    offerId: int
    product: ProductInfo
    unitsSold: int
    onHand: int
    declaredStockKeys: Optional[int] = None
    declaredStockReservedKeys: int
    inventoryReservedKeys: int
    status: int
    sellingPrice: Money
    commission: Commission
    listingPrice: Money
    isLowest: bool
    lowestPrice: Money
    automatePriceOptions: Optional[AutomatePriceOptions] = None


# --- Response Wrapper ---

class OffersResponse(BaseModel):
    message: str
    statusCode: int
    data: List[OfferItem]
    totalPages: int


class Region(BaseModel):
    id: int
    name: str


class ProductItem(BaseModel):
    productId: int
    title: str
    image: Optional[str] = None
    slug: str
    platform: str
    genres: List[str] = []
    regions: List[Region]
    regionName: str
    productTypes: List[str]
    languages: List[str] = []
    minPrice: float
    maxPrice: float
    productVersion: Optional[str] = None
    worksOn: List[str] = []
    productTag: Optional[str] = None
    releaseDate: Optional[str] = None  # Có thể null (VD: Google Play Gift Card)

    # activationCountries đã bị bỏ qua


class ProductsResponse(BaseModel):
    statusCode: int
    message: str
    data: List[ProductItem]


class UpdateOfferResponse(BaseModel):
    message: str
    statusCode: int
    data: Dict[str, Any] = {}


class CompetitionPrice(BaseModel):
    amount: float
    currency: str


class CompetitionOffer(BaseModel):
    merchantName: str
    isInStock: bool
    canBePurchased: bool
    belongsToYou: bool
    price: CompetitionPrice


class CompetitionsData(BaseModel):
    totalCount: int
    offers: List[CompetitionOffer]


class ProductCompetitionsResponse(BaseModel):
    statusCode: int
    message: str
    pid: int
    competitions: CompetitionsData


class PriceDetail(BaseModel):
    yourPrice: float  # Giá gốc (Base Price) - 12.82
    retailPrice: float  # Giá hiển thị (Retail Price) - 13.69


class AutomatePriceOptions(BaseModel):
    automatePriceStatus: str
    lowerPriceLimit: Optional[float]
    higherPriceLimit: Optional[float]
    priceChangeInterval: Optional[int]
    priceChangeFactor: Optional[float]


class SingleOfferInfo(BaseModel):
    offerId: int
    slug: str
    title: str
    yourPrice: str  # Lưu ý: API trả về string "13.6900" ở root, nhưng float ở trong object price
    status: int
    productId: int
    productImage: str
    description: str
    platform: str
    totalAvailable: int  # Stock thực tế
    commission: float
    price: PriceDetail  # Object chứa giá chi tiết
    automatePriceOptions: Optional[AutomatePriceOptions] = None


class StockKey(BaseModel):
    keyId: int
    value: str
    status: int


class StockInfo(BaseModel):
    totalCount: int
    keys: List[StockKey] = []


class SingleOfferData(BaseModel):
    offer: SingleOfferInfo
    stock: StockInfo
    pages: int


class SingleOfferResponse(BaseModel):
    message: str
    statusCode: int
    data: SingleOfferData
