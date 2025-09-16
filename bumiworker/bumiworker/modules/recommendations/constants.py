from typing import Final, Dict, List, Set

PRICES: Final[Dict[str, float]] = {
    "Standard": 0.023,
    "IT_FA": 0.023,
    "IT_IA": 0.0125,
    "IT_AIA": 0.0040,
    "Glacier": 0.0036,
    "Glacier Flexible Retrieval": 0.0036,
    "Glacier Instant Retrieval": 0.0040,
    "Glacier Deep Archive": 0.00099,
    "Deep Archive": 0.00099,
}

IT_MONITOR_FEE_PER_1000: Final[float] = 0.0000025

RETURN_LIMIT: Final[int] = 3
BYTES_PER_GIB: Final[int] = 1024 ** 3

ACCESS_PATTERNS: Final[List[str]] = ["frequent", "infrequent", "archive"]
IT_POSITIVE_STATUS: Final[Set[str]] = {"enabled", "active", "on", "true"}

FREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 30
INFREQUENT_TIER_THRESHOLD_DAYS: Final[int] = 60
