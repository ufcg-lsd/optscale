import logging
from typing import Any, Dict, List

from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase

LOG = logging.getLogger(__name__)

PRICES = {
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

IT_MONITOR_FEE_PER_1000 = 0.0025
DEFAULT_COLD30 = 0.60
DEFAULT_COLD90 = 0.40
RETURN_LIMIT = 3

def _parse_tiers_gb(tiers: List[List[Any]]) -> List[Dict[str, float]]:
    out = []
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
    return out

def _current_monthly_cost(total_gb: float, tiers_gb: List[Dict[str, float]]) -> float:
    if tiers_gb:
        cost = 0.0
        for item in tiers_gb:
            price = PRICES.get(item["name"], PRICES["Standard"])
            cost += item["gb"] * price
        return cost
    return total_gb * PRICES["Standard"]

def _intelligent_tiering_cost(total_gb: float, eligible_objects: int, cold30: float, cold90: float) -> float:
    cold30 = max(0.0, min(1.0, cold30))
    cold90 = max(0.0, min(cold30, cold90))
    f_fa = 1.0 - cold30
    f_ia = cold30 - cold90
    f_aia = cold90
    storage = total_gb * (f_fa * PRICES["IT_FA"] + f_ia * PRICES["IT_IA"] + f_aia * PRICES["IT_AIA"])
    monitor = (eligible_objects / 1000.0) * IT_MONITOR_FEE_PER_1000
    return storage + monitor

class S3IntelligentTiering(S3AbandonedBucketsBase):
    SUPPORTED_CLOUD_TYPES = ["aws_cnr"]

    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = {
            "excluded_pools": {"default": {}, "clean_func": self.clean_excluded_pools},
            "skip_cloud_accounts": {"default": []},
        }

    def _aggregate_resources(self, cloud_account_id: str) -> List[Dict[str, Any]]:
        pipeline = [
            {"$match": {
                "resource_type": "Bucket",
                "cloud_account_id": cloud_account_id,
                "deleted_at": 0
            }},
            {"$project": {
                "_id": 0,
                "cloud_account_id": 1,
                "bucket_name": {"$ifNull": ["$name", "$cloud_resource_id"]},
                "it_status_bucket": "$meta.it_status_bucket",
                "tiers": "$meta.tiers",
                "last_checked": "$meta.last_checked"
            }}
        ]
        return list(self.mongo_client.restapi.resources.aggregate(pipeline))

    def _candidate_and_saving(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        it_status = str(doc.get("it_status_bucket", "")).lower()
        it_on = it_status in {"enabled", "active", "on", "true"}
        if it_on:
            return {"is_candidate": False, "saving": 0.0, "is_with_it": True}
        tiers_gb = _parse_tiers_gb(doc.get("tiers") or [])
        total_gb = sum(x["gb"] for x in tiers_gb) if tiers_gb else 0.0
        eligible_objects = 0
        cost_now = _current_monthly_cost(total_gb, tiers_gb)
        cost_it = _intelligent_tiering_cost(total_gb, eligible_objects, DEFAULT_COLD30, DEFAULT_COLD90)
        saving = max(0.0, cost_now - cost_it)
        return {"is_candidate": True, "saving": saving, "is_with_it": False}

    def _cloud_account_names(self) -> Dict[str, str]:
        try:
            return {a["id"]: a.get("name") for a in self.get_cloud_accounts()}
        except Exception:
            return {}

    def get(self, **kwargs) -> List[Dict[str, Any]]:
        options = self.get_options()
        excluded_pools = set((options.get("excluded_pools") or {}).keys())
        skip_accounts = set(options.get("skip_cloud_accounts") or [])
        ca_names = self._cloud_account_names()
        items: List[Dict[str, Any]] = []
        total_saving = 0.0
        total_count = 0

        for ca in self.get_cloud_accounts():
            ca_id = ca["id"]
            if ca_id in skip_accounts:
                continue
            docs = self._aggregate_resources(ca_id)
            for d in docs:
                if excluded_pools and d.get("pool_id") in excluded_pools:
                    continue
                eval_res = self._candidate_and_saving(d)
                if not eval_res["is_candidate"]:
                    continue
                total_count += 1
                total_saving += eval_res["saving"]
                items.append({
                    "resource_id": d.get("bucket_name"),
                    "resource_name": d.get("bucket_name"),
                    "cloud_resource_id": d.get("bucket_name"),
                    "region": None,
                    "cloud_account_id": d.get("cloud_account_id"),
                    "cloud_type": "aws_cnr",
                    "owner": {"id": None, "name": None},
                    "pool": {"id": None, "name": None, "purpose": None},
                    "is_excluded": False,
                    "is_with_intelligent_tiering": eval_res["is_with_it"],
                    "detected_at": self.created_at,
                    "cloud_account_name": ca_names.get(d.get("cloud_account_id")),
                    "saving": round(eval_res["saving"], 2),
                })

        # result = {
        #     "intelligent_tiering": {
        #         "count": total_count,
        #         "saving": round(total_saving, 2),
        #         "options": {
        #             "excluded_pools": options.get("excluded_pools") or {},
        #             "skip_cloud_accounts": options.get("skip_cloud_accounts") or [],
        #         },
        #         "items": items
        #     }
        # }
        return items

def main(organization_id, config_client, created_at, **kwargs):
    return S3IntelligentTiering(organization_id, config_client, created_at).get()

def get_module_email_name():
    return "S3 Intelligent-Tiering candidates"

