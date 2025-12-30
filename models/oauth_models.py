from pydantic import BaseModel


class TokenData(BaseModel):
    token: str


class AuthResponse(BaseModel):
    statusCode: int
    message: str
    data: TokenData
