import logging

from clients.driffle_client import DriffleClient
from models.driffle_models import OffersResponse

logger = logging.getLogger(__name__)


class DriffleService:
    def __init__(self, client: DriffleClient):
        self.client = client



