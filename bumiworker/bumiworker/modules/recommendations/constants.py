from typing import Final, Dict, List, Set

CATEGORY_MAP: Final[Dict[str, List[str]]] = {
            "frequent": [
                "standard",
                "express one zone",
            ],
            "infrequent": [
                "standard-ia",
                "one zone-ia",
                "one zone-infrequent access",
            ],
            "archive": [
                "glacier",
                "glacier ir",  # Glacier Instant Retrieval (as stored in DB)
                "glacier instant retrieval",
                "glacier flexible retrieval",
                "deep archive",  # Deep Archive (as stored in DB)
                "glacier deep archive",
            ],
        }

RETURN_LIMIT: Final[int] = 3
BYTES_PER_GIB: Final[int] = 1024 ** 3

ACCESS_PATTERNS: Final[List[str]] = ["frequent", "infrequent", "archive"]
IT_POSITIVE_STATUS: Final[Set[str]] = {"enabled", "active", "on", "true"}

FREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 30
INFREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 60

IT_MONITOR_FEE_PER_1000 = 0.0000025
