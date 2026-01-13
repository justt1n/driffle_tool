import asyncio
import logging
import time
from typing import Dict, Optional

import httpx

from constants import DEFAULT_HEADER
from models.oauth_models import AuthResponse
from utils.config import settings


class AuthHandler:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.token_url = settings.AUTH_URL

        self._auth_payload = {
            "apiKey": settings.AUTH_SECRET,
        }

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        self._lock = asyncio.Lock()

        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers=DEFAULT_HEADER
        )

    async def get_auth_headers(self) -> Dict[str, str]:
        if self._access_token and time.time() < self._token_expires_at:
            return {"Authorization": f"Bearer {self._access_token}"}

        async with self._lock:
            if self._access_token and time.time() < self._token_expires_at:
                return {"Authorization": f"Bearer {self._access_token}"}

            self.logger.info("Token is invalid or expired (inside lock), getting a new one.")
            await self._get_new_token()

        return {"Authorization": f"Bearer {self._access_token}"}

    async def _get_new_token(self) -> None:
        self.logger.info("Requesting new token using apiKey...")
        try:
            response = await self._client.post(
                self.token_url,
                json=self._auth_payload
            )

            response.raise_for_status()

            resp_data = AuthResponse.model_validate(response.json())

            self._access_token = resp_data.data.token

            self._token_expires_at = time.time() + 600  # Token hợp lệ trong 10 phút

            self.logger.info("Successfully acquired new access token.")

        except httpx.HTTPStatusError as e:
            self.logger.error(f"Token request failed: {e.response.status_code} - {e.response.text}")
            raise ConnectionError("Failed to perform token request.") from e
        except Exception as e:
            self.logger.error(f"An error occurred during auth: {str(e)}")
            raise

    async def close(self):
        await self._client.aclose()
