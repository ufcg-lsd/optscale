from typing import Final, Dict, List, Set

CATEGORY_MAP: Final[Dict[str, List[str]]] = {
            "frequent": [
                "standard",
                "express one zone",
            ],
            "infrequent": [
                "standard-ia",
                "one zone-infrequent access",
                "one zone-ia",
            ],
            "archive": [
                "glacier instant retrieval",
                "glacier flexible retrieval",
                "glacier deep archive",
                "glacier ir",
                "glacier",
                "deep archive",
            ],
        }

RETURN_LIMIT: Final[int] = 3
BYTES_PER_GIB: Final[int] = 1024 ** 3

ACCESS_PATTERNS: Final[List[str]] = ["frequent", "infrequent", "archive"]
IT_POSITIVE_STATUS: Final[Set[str]] = {"enabled", "active", "on", "true"}

FREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 30
INFREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 60

IT_MONITOR_FEE_PER_1000 = 0.0000025

ACCESS_TIER_TO_PRICE_TIER: Final[Dict[str, str]] = {
    "frequent": "FA",
    "infrequent": "IA",
    "archive": "AIA"
}
