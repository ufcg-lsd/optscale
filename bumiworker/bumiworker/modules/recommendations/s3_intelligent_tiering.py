import logging
from typing import Any, Dict, List, Union, Optional
from datetime import datetime, date, timedelta

from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase
from bumiworker.bumiworker.modules.base import DAYS_IN_MONTH
from tools.cloud_adapter.cloud import Cloud as CloudAdapter
from .constants import (
    RETURN_LIMIT,
    BYTES_PER_GIB,
    ACCESS_PATTERNS,
    IT_POSITIVE_STATUS,
    FREQUENT_TIER_THRESHOLD_DAYS,
    INFREQUENT_TIER_THRESHOLD_DAYS,
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
        self._it_price_cache: Dict[str, float] = {}

    def _aggregate_resources(self, cloud_account_id: str) -> List[Dict[str, Any]]:
        """
        Pull bucket docs for the given cloud account with only the fields we need
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
                "size_gb": "$meta.size_gb",
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
            docs = list(self.mongo_client.restapi.resources.aggregate(pipeline))
        except Exception as exc:
            LOG.warning("it_docs error: %s", str(exc))
            return []
        LOG.debug("it_docs ok")
        return docs

    def _candidate_and_saving(
        self,
        doc: Dict[str, Any],
        cloud_account: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Core decision point: determine if bucket is an IT candidate and compute saving.

        Candidate rules (short version):
          1) Skip if IT already enabled.
          2) Require positive total_gb and object_count.
          3) Access must NOT be 'frequent'.
          4) Skip if lifecycle exists (flag or non-empty rules).
          5) Require some 'Standard' GB present (typical migration target).
          6) Saving = max(0, current_cost - projected_IT_cost).
        """
        false_candidate = {"is_candidate": False, "saving": 0.0, "is_with_it": True}

        try:
            it_status = str(doc.get("it_status_bucket", "")).lower()
            it_on = it_status in IT_POSITIVE_STATUS
            if it_on:
                return false_candidate

            tiers_gb = _parse_tiers_gb(doc.get("tiers") or [])
            total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
            if total_gb <= 0.0:
                return false_candidate

            today = datetime.utcfromtimestamp(self.created_at).date() if self.created_at else date.today()
            access_tier = _classify_access_tier_from_last_checked(doc.get("last_checked"), today)
            if access_tier == "frequent":
                return false_candidate

            has_lifecycle_flag = bool(doc.get("has_lifecycle"))
            lifecycle_rules = doc.get("lifecycle_rules")
            if has_lifecycle_flag or (isinstance(lifecycle_rules, list) and len(lifecycle_rules) > 0):
                return false_candidate

            object_count = int(doc.get("object_count") or 0)
            if object_count <= 0:
                return false_candidate

            has_standard_positive = any(
                (str(x["name"]).lower() == "standard" and float(x["gb"]) > 0.0)
                for x in tiers_gb
            )
            if not has_standard_positive:
                return false_candidate

            real_saving = self._real_saving_payload(
                doc, total_gb, today, cloud_account)
            if not real_saving:
                return false_candidate
            LOG.debug("it_eval ok")
            result = {"is_candidate": True, "saving": real_saving["saving"], "is_with_it": False}
            result.update(real_saving)
            return result
        except Exception as exc:
            LOG.warning("it_eval error: %s", str(exc))
            return false_candidate

    def _real_saving_payload(
        self,
        doc: Dict[str, Any],
        total_gb: float,
        today: date,
        cloud_account: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, float]]:
        """
        Build a dict with real saving metrics using ClickHouse expenses and Pricing API data.
        """
        if not cloud_account:
            return None
        resource_id = doc.get("resource_id")
        cloud_account_id = doc.get("cloud_account_id")
        if not resource_id or not cloud_account_id:
            return None

        size_gb = doc.get("size_gb", total_gb)
        try:
            size_gb_value = float(size_gb)
        except (TypeError, ValueError):
            size_gb_value = float(total_gb)
        if size_gb_value <= 0.0:
            return None

        real_cost = self._bucket_monthly_cost(cloud_account_id, resource_id, today)
        if real_cost is None:
            return None

        price_it = self._get_intelligent_tiering_price(cloud_account)
        if price_it is None:
            return None

        cost_if_it = size_gb_value * price_it
        saving_real = real_cost - cost_if_it
        return {
            "saving": max(0.0, saving_real),
            "current_cost_month": real_cost,
            "cost_if_intelligent_tiering": cost_if_it,
            "size_gb": size_gb_value,
            "price_intelligent_tiering": price_it,
        }

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

    def _get_intelligent_tiering_price(
        self,
        cloud_account: Dict[str, Any]
    ) -> Optional[float]:
        """
        Fetch Intelligent-Tiering GB-month price using the CloudAdapter Pricing API.
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
        try:
            price_payload = adapter.get_prices({
                "resource_type": "Bucket",
                "storage_class": "INTELLIGENT_TIERING",
            })
        except Exception as exc:
            LOG.warning("it_price lookup failed for %s: %s", cloud_account_id, str(exc))
            return None

        entry: Optional[Dict[str, Any]] = None
        if isinstance(price_payload, list) and price_payload:
            entry = price_payload[0]
        elif isinstance(price_payload, dict):
            entry = price_payload
        if not entry:
            return None
        price_value = self._normalize_price_value(entry.get("price"))
        if price_value is None:
            return None
        self._it_price_cache[cloud_account_id] = price_value
        return price_value

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
        cloud_accounts = self.get_cloud_accounts()
        for ca in cloud_accounts.values():
            ca_id = self._extract_cloud_account_id(ca)
            if not ca_id:
                LOG.warning("Skipping cloud account with unknown structure: %r", ca)
                continue
            if ca_id in skip_accounts:
                continue

            docs = self._aggregate_resources(ca_id)
            for d in docs:
                if excluded_pools and d.get("pool_id") in excluded_pools:
                    continue

                eval_res = self._candidate_and_saving(d, ca)
                if not eval_res["is_candidate"]:
                    continue

                item = {
                    "resource_id": d.get("resource_id"),
                    "resource_name":  d.get("bucket_name"),
                    "cloud_resource_id":  d.get("bucket_name"),
                    "region": d.get("region"),
                    "cloud_account_id": d.get("cloud_account_id"),
                    "cloud_type": "aws_cnr",
                    "owner": self._extract_owner(
                        d.get("owner_id") or d.get("employee_id"), employees),
                    "pool": self._extract_pool(
                        d.get("pool_id"), pools),
                    "is_excluded": d.get("pool_id") in excluded_pools,
                    "is_with_intelligent_tiering": eval_res["is_with_it"],
                    "detected_at": self.created_at,
                    "cloud_account_name": ca_names.get(d.get("cloud_account_id")),
                    "saving": round(eval_res["saving"], 2),
                }
                if "current_cost_month" in eval_res:
                    item["current_cost_month"] = round(eval_res["current_cost_month"], 2)
                if "cost_if_intelligent_tiering" in eval_res:
                    item["cost_if_intelligent_tiering"] = round(
                        eval_res["cost_if_intelligent_tiering"], 2)
                if "size_gb" in eval_res:
                    item["size_gb"] = round(eval_res["size_gb"], 3)
                if "price_intelligent_tiering" in eval_res:
                    item["price_intelligent_tiering"] = round(
                        eval_res["price_intelligent_tiering"], 6)
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
