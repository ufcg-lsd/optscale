import logging
from typing import Any, Dict, List, Union, Optional
from datetime import datetime, date

from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase
from .constants import (
    CATEGORY_MAP,
    ACCESS_PATTERNS,
    IT_POSITIVE_STATUS,
    FREQUENT_TIER_THRESHOLD_DAYS,
    INFREQUENT_TIER_THRESHOLD_DAYS,
    IT_MONITOR_FEE_PER_1000,
)

LOG = logging.getLogger(__name__)


def _parse_tiers_gb(tiers: List[Any]) -> List[Dict[str, float]]:
    """
    Normalize 'tiers' into [{'name': <tier_name>, 'gb': <float>}].
    Accepts list-of-lists or list-of-dicts formats commonly found in meta.tiers.
    """
    out: List[Dict[str, float]] = []
    if not tiers:
        return out
    for t in tiers:
        if isinstance(t, list) and len(t) >= 2:
            name = str(t[0])
            try:
                gb = float(t[1])
            except Exception:
                continue
            out.append({"name": name, "gb": gb})
        elif isinstance(t, dict):
            name = str(t.get("name") or t.get("tier") or "Standard")
            val = t.get("gb", t.get("size_gb", t.get("size")))
            try:
                gb = float(val)
            except Exception:
                continue
            out.append({"name": name, "gb": gb})
    return out


def _current_monthly_cost(total_gb: float, tiers_gb: List[Dict[str, float]]) -> float:
    """
    Estimate current monthly storage cost for the bucket.
    - If we have per-tier breakdown (tiers_gb), sum gb * PRICES[tier].
    - Otherwise, assume all at Standard price.
    """
    if tiers_gb:
        cost = 0.0
        for item in tiers_gb:
            price = PRICES.get(item["name"], PRICES["Standard"])
            cost += item["gb"] * price
        return cost
    return total_gb * PRICES["Standard"]


def _parse_date_loose(s: Any) -> Optional[date]:
    """
    Parse a date string leniently (YYYY-MM-DD or ISO-ish); return None if invalid.
    """
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        pass
    try:
        cleaned = s.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).date()
    except Exception:
        return None


def _classify_access_tier_from_last_checked(last_checked: Any, today: date) -> str:
    """
    Infer access pattern ('frequent' | 'infrequent' | 'archive') from recency:
      - ≤ 30 days since most recent 'last_checked'  -> 'frequent'
      - 31–60 days                                   -> 'infrequent'
      - > 60 days or no dates                        -> 'archive'
    """
    dates: List[date] = []
    if isinstance(last_checked, list):
        for item in last_checked:
            d = _parse_date_loose(item)
            if d:
                dates.append(d)
    if not dates:
        return ACCESS_PATTERNS[2]
    most_recent = max(dates)
    delta = (today - most_recent).days
    if delta <= FREQUENT_TIER_THRESHOLD_DAYS:
        return ACCESS_PATTERNS[0]
    elif delta <= INFREQUENT_TIER_THRESHOLD_DAYS:
        return ACCESS_PATTERNS[1]
    else:
        return ACCESS_PATTERNS[2]


def _it_price_per_gb_for_access_tier(access_tier: str) -> float:
    """
    Map inferred access class to the corresponding IT storage price.
    """
    tier = (access_tier or "").lower()
    if tier == ACCESS_PATTERNS[1]:
        return PRICES["IT_IA"]
    if tier == ACCESS_PATTERNS[2]:
        return PRICES["IT_AIA"]
    return PRICES["IT_FA"]


def _intelligent_tiering_cost_by_access(total_gb: float, eligible_objects: int, access_tier: str) -> float:
    """
    Project monthly cost under S3 Intelligent-Tiering for a bucket:
      IT storage cost (per GB) + monitoring fee per 1,000 objects.

      cost_it = total_gb * IT_price(access_tier) + (objects / 1000) * IT_MONITOR_FEE_PER_1000
    """
    price_per_gb = _it_price_per_gb_for_access_tier(access_tier)
    storage = total_gb * price_per_gb
    monitor = float(eligible_objects) * IT_MONITOR_FEE_PER_1000
    return storage + monitor


class S3IntelligentTiering(S3AbandonedBucketsBase):
    """
    Identify S3 buckets that are good candidates for enabling Intelligent-Tiering
    and estimate the potential monthly saving.
    """
    SUPPORTED_CLOUD_TYPES = ["aws_cnr"]

    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = {
            "excluded_pools": {"default": {}, "clean_func": self.clean_excluded_pools},
            "skip_cloud_accounts": {"default": []},
        }
        self._adapter_cache: Dict[str, Any] = {}
        self._it_price_cache: Dict[str, Dict[str, float]] = {}  # Cache prices per tier

    def _aggregate_resources(self, cloud_account_id: str) -> List[Dict[str, Any]]:
        """
        Pull bucket resources for the given cloud account with only the fields we need
        for candidate selection and saving computation.
        """
        pipeline = [
            {"$match": {
                "resource_type": "Bucket",
                "cloud_account_id": cloud_account_id,
                "active": True,
                "deleted_at": 0
            }},
            {"$project": {
                "_id": 0,
                "resource_id": "$_id",
                "cloud_account_id": 1,
                "bucket_name": {"$ifNull": ["$name", "$cloud_resource_id"]},
                "it_status_bucket": "$meta.it_status_bucket",
                "tiers": "$meta.tiers",
                "object_count": "$meta.object_count",
                "pool_id": 1,
                "owner_id": "$owner_id",
                "employee_id": "$employee_id",
                "region": 1,
                "last_checked": "$meta.last_checked",
                "has_lifecycle": "$meta.has_lifecycle",
                "lifecycle_rules": "$meta.lifecycle_rules"
            }}
        ]
        try:
            resources = list(self.mongo_client.restapi.resources.aggregate(pipeline))
        except Exception as exc:
            LOG.warning("it_resources error: %s", str(exc))
            return []
        LOG.debug("it_resources ok")
        return resources
    

    def _classify_wrong_access_tier(self, category_bucket: str, last_checked: List[Any]) -> bool:
        """
        Classify the access tier of the bucket.
        """
        today = datetime.utcfromtimestamp(self.created_at).date() if self.created_at else date.today()
        access_tier = _classify_access_tier_from_last_checked(last_checked, today)
        if access_tier == category_bucket:
            return False
        return True

    def _classify_category_from_tier(self, tier: str) -> str:
        """
        Return the access category ('frequent' | 'infrequent' | 'archive' | 'unknown')
        based on the AWS storage tier.

        Mapping follows the table:
        - Frequent   → ["standard", "express one zone"]
        - Infrequent → ["standard-ia", "one zone-infrequent access"]
        - Archive    → ["glacier instant retrieval",
                        "glacier flexible retrieval",
                        "glacier deep archive"]
        """

        if not isinstance(tier, str):
            return "unknown"

        tier_norm = tier.strip().lower()

        for category, aws_tiers in CATEGORY_MAP.items():
            if tier_norm in (t.lower() for t in aws_tiers):
                return category

        return "unknown"


    def _is_candidate(self, resource: Dict[str, Any]) -> bool:
        """
        Check if the bucket is a candidate for Intelligent-Tiering.

        A bucket is considered a candidate if all of the following conditions are met:
        1) Intelligent-Tiering is not already enabled on the bucket.
        2) Bucket has positive total size (GB) and object count.
        3) Access pattern does not match the current storage class category
           (e.g., bucket is in Standard class but access pattern is infrequent/archive).
        4) No lifecycle policies are configured.

        Returns:
            bool: True if bucket is a candidate for IT, False otherwise.
        """
        it_status = str(resource.get("it_status_bucket", "")).lower()
        it_on = it_status in IT_POSITIVE_STATUS
        if it_on:
            return False
        tiers_gb = _parse_tiers_gb(resource.get("tiers") or [])
        total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
        if total_gb <= 0.0:
            return False

        has_lifecycle_flag = bool(resource.get("has_lifecycle"))
        lifecycle_rules = resource.get("lifecycle_rules")
        if has_lifecycle_flag or (isinstance(lifecycle_rules, list) and len(lifecycle_rules) > 0):
            return False
        
        object_count = int(resource.get("object_count") or 0)
        if object_count <= 0:
            return False
        
        tiers_gb = _parse_tiers_gb(resource.get("tiers") or [])
        category_bucket = "unknown"
        if tiers_gb:
            standard_tier = next((t for t in tiers_gb if str(t["name"]).lower() == "standard"), None)
            if standard_tier:
                category_bucket = self._classify_category_from_tier(standard_tier["name"])
            else:
                largest_tier = max(tiers_gb, key=lambda x: x["gb"])
                category_bucket = self._classify_category_from_tier(largest_tier["name"])
        
        wrong_access_tier = self._classify_wrong_access_tier(category_bucket, resource.get("last_checked"))
        if not wrong_access_tier:
            return False
        
        return True

   
    def _real_saving_payload(
        self,
        resource: Dict[str, Any],
        total_gb: float,
        today: date,
        cloud_account: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, float]]:
        """
        Build a dict with real saving metrics using ClickHouse expenses and Pricing API data.
        Now uses improved calculation considering different IT tiers and monitoring fees.
        """
        if not cloud_account:
            return None
        resource_id = resource.get("resource_id")
        cloud_account_id = resource.get("cloud_account_id")
        if not resource_id or not cloud_account_id:
            return None

        size_gb = resource.get("size_gb", total_gb)
        try:
            size_gb_value = float(size_gb)
        except (TypeError, ValueError):
            size_gb_value = float(total_gb)
        if size_gb_value <= 0.0:
            return None

        real_cost = self._bucket_monthly_cost(cloud_account_id, resource_id, today)
        if real_cost is None:
            return None

        access_tier = _classify_access_tier_from_last_checked(resource.get("last_checked"), today)
        object_count = int(resource.get("object_count") or 0)

        it_cost_breakdown = self._calculate_it_cost(
            size_gb_value, access_tier, object_count, cloud_account
        )
        if it_cost_breakdown is None:
            return None

        cost_if_it = it_cost_breakdown["total_cost"]
        saving_real = real_cost - cost_if_it


        result = {
            "saving": max(0.0, saving_real),
            "current_cost_month": real_cost,
            "cost_if_intelligent_tiering": cost_if_it,
            "size_gb": size_gb_value,
            "price_intelligent_tiering": it_cost_breakdown["price_per_gb"],
            "it_storage_cost": it_cost_breakdown["storage_cost"],
            "it_monitoring_cost": it_cost_breakdown["monitoring_cost"],
        }
        return result

    def _bucket_monthly_cost(
        self,
        cloud_account_id: str,
        resource_id: str,
        today: date
    ) -> Optional[float]:
        """
        Sum daily costs for the bucket over the last month (ClickHouse expenses).
        """
        if not cloud_account_id or not resource_id:
            return None
        start_date = today - timedelta(days=DAYS_IN_MONTH)
        query = """
            SELECT date, sum(cost)
            FROM expenses
            WHERE cloud_account_id = %(cloud_account_id)s
              AND resource_id = %(resource_id)s
              AND date >= %(start_date)s
              AND date < %(end_date)s
            GROUP BY date
        """
        try:
            rows = self.clickhouse_client.query(
                query=query,
                parameters={
                    "cloud_account_id": cloud_account_id,
                    "resource_id": resource_id,
                    "start_date": start_date,
                    "end_date": today,
                }
            ).result_rows
        except Exception as exc:
            LOG.warning("it_clickhouse error for %s: %s", resource_id, str(exc))
            return None
        total = 0.0
        for _, cost in rows:
            try:
                total += float(cost)
            except (TypeError, ValueError):
                continue
        return total


    def _get_intelligent_tiering_prices(
        self,
        cloud_account: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Fetch Intelligent-Tiering prices per tier using the CloudAdapter Pricing API.
        Returns a dict with prices for each tier (FA, IA, AIA, DAA) or uses constants as fallback.
        Uses cache to avoid repeated API calls.
        """
        cloud_account_id = self._extract_cloud_account_id(cloud_account)
        if not cloud_account_id:
            return None

        cached = self._it_price_cache.get(cloud_account_id)
        if cached is not None:
            return cached

        adapter = self._cloud_adapter_for_account(cloud_account_id, cloud_account)
        if not adapter:
            return None

        prices = {}
        tier_mappings = {
            "FA": ["Intelligent-Tiering Frequent Access", "Intelligent Tiering - Frequent"],
            "IA": ["Intelligent-Tiering Infrequent Access", "Intelligent Tiering - Infrequent"],
            "AIA": ["Intelligent-Tiering Archive Instant Access", "Intelligent Tiering - Archive Access"],
            "DAA": ["Intelligent-Tiering Deep Archive Access", "Intelligent Tiering - Deep Archive Access"],
        }

        for tier_key, storage_class_names in tier_mappings.items():
            tier_price = None
            for storage_class_name in storage_class_names:
                try:
                    price_payload = adapter.get_prices({
                        "resource_type": "Bucket",
                        "storage_class": storage_class_name,
                    })
                    if isinstance(price_payload, list) and price_payload:
                        entry = price_payload[0]
                        tier_price = self._normalize_price_value(entry.get("price"))
                        if tier_price is not None:
                            break
                except Exception as exc:
                    LOG.debug("it_price lookup for %s failed: %s", storage_class_name, str(exc))
                    continue
            if tier_price is None:
                return None 
            prices[tier_key] = tier_price

        # Cache the results
        self._it_price_cache[cloud_account_id] = prices
        return prices

    def _calculate_it_cost(
        self,
        size_gb: float,
        access_tier: str,
        object_count: int,
        cloud_account: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate Intelligent Tiering cost considering:
        - Consider the access tier to define the class of the bucket
        - Storage cost
        - Monitoring fee per 1000 objects
        
        Returns dict with the total cost, storage cost, monitoring cost, monitoring price per 1000 objects.
        """
        if size_gb <= 0.0 or object_count <= 0:
            return None

        tier_prices = self._get_intelligent_tiering_prices(cloud_account)
        
        price_per_gb = tier_prices.get(access_tier, 0.0)
        total_storage_cost = size_gb * price_per_gb

        monitoring_price_per_1000 = IT_MONITOR_FEE_PER_1000
        monitoring_cost = (object_count / 1000.0) * monitoring_price_per_1000

        total_cost = total_storage_cost + monitoring_cost

        return {
            "total_cost": total_cost,
            "storage_cost": total_storage_cost,
            "monitoring_cost": monitoring_cost,
            "monitoring_price_per_1000": monitoring_price_per_1000,
        }

    def _cloud_adapter_for_account(
        self,
        cloud_account_id: str,
        cloud_account: Dict[str, Any]
    ):
        cached = self._adapter_cache.get(cloud_account_id)
        if cached:
            return cached
        config = dict(cloud_account or {})
        nested_cfg = config.pop("config", None)
        if isinstance(nested_cfg, dict):
            config.update(nested_cfg)
        try:
            adapter = CloudAdapter.get_adapter(config)
        except Exception as exc:
            LOG.warning("it_adapter error for %s: %s", cloud_account_id, str(exc))
            return None
        self._adapter_cache[cloud_account_id] = adapter
        return adapter

    @staticmethod
    def _normalize_price_value(raw_price: Any) -> Optional[float]:
        if isinstance(raw_price, dict):
            for key in ("USD", "usd"):
                price_candidate = raw_price.get(key)
                if price_candidate is not None:
                    try:
                        return float(price_candidate)
                    except (TypeError, ValueError):
                        pass
            try:
                return float(next(iter(raw_price.values())))
            except (StopIteration, (TypeError, ValueError)):
                return None
        try:
            return float(raw_price)
        except (TypeError, ValueError):
            return None

    def _cloud_account_names(self) -> Dict[str, str]:
        """
        Best-effort mapping {cloud_account_id: cloud_account_name}.
        """
        try:
            out: Dict[str, str] = {}
            for a in self.get_cloud_accounts():
                if isinstance(a, str):
                    continue
                if isinstance(a, dict):
                    aid = a.get("id") or a.get("_id")
                    if aid:
                        out[aid] = a.get("name")
            return out
        except Exception:
            return {}

    def _extract_cloud_account_id(self, ca: Union[str, Dict[str, Any]]) -> str:
        """
        Normalize cloud account input into its id string.
        """
        if isinstance(ca, str):
            return ca
        if isinstance(ca, dict):
            return ca.get("id") or ca.get("_id")
        return ""

    def get(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Iterate cloud accounts, fetch buckets, apply candidate logic,
        and return a list of candidate items with computed 'saving'.
        """
        options = self.get_options()
        excluded_pools = set((options.get("excluded_pools") or {}).keys())
        skip_accounts = set(options.get("skip_cloud_accounts") or [])
        ca_names = self._cloud_account_names()
        employees = self.get_employees()
        pools = self.get_pools()

        items: List[Dict[str, Any]] = []
        for ca in self.get_cloud_accounts():
            ca_id = self._extract_cloud_account_id(ca)
            if not ca_id:
                LOG.warning("Skipping cloud account with unknown structure: %r", ca)
                continue
            if ca_id in skip_accounts:
                continue

            resources = self._aggregate_resources(ca_id)
            today = datetime.utcfromtimestamp(self.created_at).date() if self.created_at else date.today()
            
            for d in resources:
                if excluded_pools and d.get("pool_id") in excluded_pools:
                    continue

                # Check if bucket is a candidate
                if not self._is_candidate(d):
                    continue

                # Calculate saving with improved IT cost calculation
                tiers_gb = _parse_tiers_gb(d.get("tiers") or [])
                total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
                
                saving_data = self._real_saving_payload(d, total_gb, today, ca)
                if not saving_data or saving_data["saving"] <= 0.0:
                    # Only include if IT would be cheaper
                    continue

                # Determine IT status
                it_status = str(d.get("it_status_bucket", "")).lower()
                is_with_it = it_status in IT_POSITIVE_STATUS

                item = {
                    "resource_id": d.get("resource_id"),
                    "resource_name": d.get("bucket_name"),
                    "cloud_resource_id": d.get("bucket_name"),
                    "region": d.get("region"),
                    "cloud_account_id": d.get("cloud_account_id"),
                    "cloud_type": "aws_cnr",
                    "owner": self._extract_owner(
                        d.get("owner_id") or d.get("employee_id"), employees),
                    "pool": self._extract_pool(
                        d.get("pool_id"), pools),
                    "is_excluded": d.get("pool_id") in excluded_pools,
                    "is_with_intelligent_tiering": is_with_it,
                    "detected_at": self.created_at,
                    "cloud_account_name": ca_names.get(d.get("cloud_account_id")),
                    "saving": round(saving_data["saving"], 2),
                }
                if "current_cost_month" in saving_data:
                    item["current_cost_month"] = round(saving_data["current_cost_month"], 2)
                if "cost_if_intelligent_tiering" in saving_data:
                    item["cost_if_intelligent_tiering"] = round(
                        saving_data["cost_if_intelligent_tiering"], 2)
                if "size_gb" in saving_data:
                    item["size_gb"] = round(saving_data["size_gb"], 3)
                if "price_intelligent_tiering" in saving_data:
                    item["price_intelligent_tiering"] = round(
                        saving_data["price_intelligent_tiering"], 6)
                items.append(item)
        LOG.debug("it_list ok")
        return items


def main(organization_id, config_client, created_at, **kwargs):
    """
    Entry point used by the worker: returns (data, options, error).
    """
    mod = S3IntelligentTiering(organization_id, config_client, created_at)
    data = mod.get()
    options = mod.get_options()
    error = None
    return data, options, error


def get_module_email_name():
    return "S3 Intelligent-Tiering candidates"
