import re
from typing import Optional


def get_prod_id(url: str) -> Optional[int]:
    match = re.search(r'i(\d+)$', url)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def get_offer_id(url_or_id: str) -> Optional[str]:
    uuid_pattern = r'([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})'
    match = re.search(uuid_pattern, url_or_id)
    if match:
        return match.group(1)
    return None
