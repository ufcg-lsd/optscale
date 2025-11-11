import logging
from typing import Any, Dict, List, Union, Optional
from datetime import datetime, date

from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase
from .constants import (
    PRICES,
    IT_MONITOR_FEE_PER_1000,
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
        return list(self.mongo_client.restapi.resources.aggregate(pipeline))

    def _candidate_and_saving(self, doc: Dict[str, Any]) -> Dict[str, Any]:
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

        eligible_objects = object_count
        cost_now = _current_monthly_cost(total_gb, tiers_gb)
        cost_it = _intelligent_tiering_cost_by_access(total_gb, eligible_objects, access_tier)

        saving = max(0.0, cost_now - cost_it)
        return {"is_candidate": True, "saving": saving, "is_with_it": False}

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

            docs = self._aggregate_resources(ca_id)
            for d in docs:
                if excluded_pools and d.get("pool_id") in excluded_pools:
                    continue

                eval_res = self._candidate_and_saving(d)
                if not eval_res["is_candidate"]:
                    continue

                items.append({
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
                })
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
