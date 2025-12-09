import logging
from typing import Any, Dict, List, Union, Optional
from datetime import datetime, date, timedelta

from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase
from bumiworker.bumiworker.modules.base import DAYS_IN_MONTH
from tools.cloud_adapter.cloud import Cloud as CloudAdapter
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
            LOG.info(
                "[IT] Aggregated %d bucket resources for cloud_account_id=%s",
                len(resources), cloud_account_id
            )
        except Exception as exc:
            LOG.error(
                "[IT] Failed to aggregate resources for cloud_account_id=%s: %s",
                cloud_account_id, str(exc), exc_info=True
            )
            return []
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
        - Infrequent → ["standard-ia", "one zone-ia", "one zone-infrequent access"]
        - Archive    → ["glacier", "glacier ir", "glacier instant retrieval",
                        "glacier flexible retrieval", "deep archive",
                        "glacier deep archive"]
        
        Handles variations in tier names as they appear in the database:
        - "Standard-IA" → infrequent
        - "Glacier IR" → archive
        - "Glacier" → archive
        - "Deep Archive" → archive
        - "RRS", "Glacier Overhead", "Deep Archive Overhead" → unknown (not real storage)
        """

        if not isinstance(tier, str):
            return "unknown"

        tier_norm = tier.strip().lower()
        
        # Skip overhead tiers (not real storage) - check before matching
        if "overhead" in tier_norm:
            LOG.info("[IT] Tier '%s' classified as 'unknown' (overhead tier)", tier)
            return "unknown"
        
        # Exact match with CATEGORY_MAP
        for category, aws_tiers in CATEGORY_MAP.items():
            if tier_norm in (t.lower() for t in aws_tiers):
                LOG.info("[IT] Tier '%s' classified as '%s'", tier, category)
                return category

        LOG.warning("[IT] Tier '%s' not found in CATEGORY_MAP, returning 'unknown'", tier)
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
        resource_id = resource.get("resource_id", "unknown")
        it_status = str(resource.get("it_status_bucket", "")).lower()
        it_on = it_status in IT_POSITIVE_STATUS
        if it_on:
            LOG.info("[IT] Bucket %s is not a candidate: IT already enabled", resource_id)
            return False
        tiers_gb = _parse_tiers_gb(resource.get("tiers") or [])
        total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
        if total_gb <= 0.0:
            LOG.info("[IT] Bucket %s is not a candidate: total_gb=%.2f", resource_id, total_gb)
            return False

        has_lifecycle_flag = bool(resource.get("has_lifecycle"))
        lifecycle_rules = resource.get("lifecycle_rules")
        if has_lifecycle_flag or (isinstance(lifecycle_rules, list) and len(lifecycle_rules) > 0):
            LOG.info("[IT] Bucket %s is not a candidate: has lifecycle policies", resource_id)
            return False
        
        object_count = int(resource.get("object_count") or 0)
        if object_count <= 0:
            LOG.info("[IT] Bucket %s is not a candidate: object_count=%d", resource_id, object_count)
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
            LOG.info(
                "[IT] Bucket %s is not a candidate: access tier matches storage category (%s)",
                resource_id, category_bucket
            )
            return False
        
        LOG.info(
            "[IT] Bucket %s is a candidate: category=%s, total_gb=%.2f, objects=%d",
            resource_id, category_bucket, total_gb, object_count
        )
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
            LOG.warning("[IT] Cannot calculate saving: cloud_account is None")
            return None
        resource_id = resource.get("resource_id")
        cloud_account_id = resource.get("cloud_account_id")
        if not resource_id or not cloud_account_id:
            LOG.warning(
                "[IT] Cannot calculate saving: missing resource_id or cloud_account_id. "
                "resource_id=%s, cloud_account_id=%s",
                resource_id, cloud_account_id
            )
            return None

        size_gb = resource.get("size_gb", total_gb)
        try:
            size_gb_value = float(size_gb)
        except (TypeError, ValueError) as exc:
            LOG.info(
                "[IT] Failed to parse size_gb=%s, using total_gb=%.2f: %s",
                size_gb, total_gb, str(exc)
            )
            size_gb_value = float(total_gb)
        if size_gb_value <= 0.0:
            LOG.warning("[IT] Cannot calculate saving: size_gb_value=%.2f <= 0", size_gb_value)
            return None

        real_cost = self._bucket_monthly_cost(cloud_account_id, resource_id, today)
        if real_cost is None:
            LOG.warning(
                "[IT] Cannot calculate saving: failed to get current cost for bucket %s",
                resource_id
            )
            return None

        access_tier = _classify_access_tier_from_last_checked(resource.get("last_checked"), today)
        object_count = int(resource.get("object_count") or 0)
        LOG.info(
            "[IT] Calculating IT cost for bucket %s: size_gb=%.2f, access_tier=%s, objects=%d",
            resource_id, size_gb_value, access_tier, object_count
        )

        it_cost_breakdown = self._calculate_it_cost(
            size_gb_value, access_tier, object_count, cloud_account
        )
        if it_cost_breakdown is None:
            LOG.warning(
                "[IT] Cannot calculate saving: failed to calculate IT cost for bucket %s",
                resource_id
            )
            return None

        cost_if_it = it_cost_breakdown["total_cost"]
        saving_real = real_cost - cost_if_it
        LOG.info(
            "[IT] Bucket %s savings calculated: current_cost=%.2f, it_cost=%.2f, saving=%.2f",
            resource_id, real_cost, cost_if_it, saving_real
        )


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
            LOG.info(
                "[IT] Retrieved %d expense rows for bucket %s (period: %s to %s)",
                len(rows), resource_id, start_date, today
            )
        except Exception as exc:
            LOG.error(
                "[IT] ClickHouse query failed for bucket %s (cloud_account_id=%s): %s",
                resource_id, cloud_account_id, str(exc), exc_info=True
            )
            return None
        total = 0.0
        for _, cost in rows:
            try:
                total += float(cost)
            except (TypeError, ValueError) as exc:
                LOG.info("[IT] Skipping invalid cost value: %s (%s)", cost, str(exc))
                continue
        LOG.info("[IT] Total monthly cost for bucket %s: %.2f", resource_id, total)
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
            LOG.warning("[IT] Cannot fetch prices: cloud_account_id is empty")
            return None

        cached = self._it_price_cache.get(cloud_account_id)
        if cached is not None:
            LOG.info("[IT] Using cached prices for cloud_account_id=%s", cloud_account_id)
            return cached

        LOG.info("[IT] Fetching IT prices from API for cloud_account_id=%s", cloud_account_id)
        adapter = self._cloud_adapter_for_account(cloud_account_id, cloud_account)
        if not adapter:
            LOG.error(
                "[IT] Cannot fetch prices: failed to get adapter for cloud_account_id=%s",
                cloud_account_id
            )
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
                            LOG.info(
                                "[IT] Found price for tier %s (%s): %.6f",
                                tier_key, storage_class_name, tier_price
                            )
                            break
                except Exception as exc:
                    LOG.warning(
                        "[IT] Price lookup failed for tier %s (%s): %s",
                        tier_key, storage_class_name, str(exc)
                    )
                    continue
            if tier_price is None:
                LOG.error(
                    "[IT] Failed to get price for tier %s (tried %d storage class names)",
                    tier_key, len(storage_class_names)
                )
                return None 
            prices[tier_key] = tier_price

        # Cache the results
        self._it_price_cache[cloud_account_id] = prices
        LOG.info(
            "[IT] Successfully fetched and cached prices for cloud_account_id=%s: %s",
            cloud_account_id, ", ".join(f"{k}=${v:.6f}" for k, v in prices.items())
        )
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
            LOG.warning(
                "[IT] Cannot calculate IT cost: size_gb=%.2f, object_count=%d",
                size_gb, object_count
            )
            return None

        tier_prices = self._get_intelligent_tiering_prices(cloud_account)
        if tier_prices is None:
            LOG.error("[IT] Cannot calculate IT cost: failed to get tier prices")
            return None
        
        price_per_gb = tier_prices.get(access_tier, 0.0)
        if price_per_gb == 0.0:
            LOG.warning(
                "[IT] No price found for access_tier=%s in tier_prices. Available tiers: %s",
                access_tier, list(tier_prices.keys())
            )
        total_storage_cost = size_gb * price_per_gb

        monitoring_price_per_1000 = IT_MONITOR_FEE_PER_1000
        monitoring_cost = (object_count / 1000.0) * monitoring_price_per_1000

        total_cost = total_storage_cost + monitoring_cost

        LOG.info(
            "[IT] IT cost breakdown: storage=%.2f (%.2f GB × $%.6f), monitoring=%.2f, total=%.2f",
            total_storage_cost, size_gb, price_per_gb, monitoring_cost, total_cost
        )

        return {
            "total_cost": total_cost,
            "storage_cost": total_storage_cost,
            "monitoring_cost": monitoring_cost,
            "monitoring_price_per_1000": monitoring_price_per_1000,
            "price_per_gb": price_per_gb,
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
            LOG.info("[IT] Successfully created adapter for cloud_account_id=%s", cloud_account_id)
        except Exception as exc:
            LOG.error(
                "[IT] Failed to create adapter for cloud_account_id=%s: %s",
                cloud_account_id, str(exc), exc_info=True
            )
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

        LOG.info(
            "[IT] Starting recommendation processing for org_id=%s. "
            "Excluded pools: %d, Skip accounts: %d",
            self.organization_id, len(excluded_pools), len(skip_accounts)
        )
        items: List[Dict[str, Any]] = []
        total_buckets_processed = 0
        total_candidates_found = 0
        
        for ca in self.get_cloud_accounts():
            ca_id = self._extract_cloud_account_id(ca)
            if not ca_id:
                LOG.warning("[IT] Skipping cloud account with unknown structure: %r", ca)
                continue
            if ca_id in skip_accounts:
                LOG.info("[IT] Skipping cloud_account_id=%s (in skip_accounts)", ca_id)
                continue

            resources = self._aggregate_resources(ca_id)
            today = datetime.utcfromtimestamp(self.created_at).date() if self.created_at else date.today()
            LOG.info(
                "[IT] Processing %d buckets for cloud_account_id=%s",
                len(resources), ca_id
            )
            
            for d in resources:
                total_buckets_processed += 1
                resource_id = d.get("resource_id", "unknown")
                
                if excluded_pools and d.get("pool_id") in excluded_pools:
                    LOG.info("[IT] Bucket %s excluded (pool_id in excluded_pools)", resource_id)
                    continue

                # Check if bucket is a candidate
                if not self._is_candidate(d):
                    continue
                
                total_candidates_found += 1

                # Calculate saving with improved IT cost calculation
                tiers_gb = _parse_tiers_gb(d.get("tiers") or [])
                total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
                
                saving_data = self._real_saving_payload(d, total_gb, today, ca)
                if not saving_data or saving_data["saving"] <= 0.0:
                    LOG.info(
                        "[IT] Bucket %s excluded: IT would not be cheaper (saving=%.2f)",
                        resource_id, saving_data["saving"] if saving_data else 0.0
                    )
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
                LOG.info(
                    "[IT] Added recommendation for bucket %s: saving=%.2f, "
                    "current_cost=%.2f, it_cost=%.2f",
                    resource_id, item["saving"],
                    item.get("current_cost_month", 0),
                    item.get("cost_if_intelligent_tiering", 0)
                )
        
        LOG.info(
            "[IT] Recommendation processing completed: "
            "processed=%d buckets, candidates=%d, recommendations=%d",
            total_buckets_processed, total_candidates_found, len(items)
        )
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
