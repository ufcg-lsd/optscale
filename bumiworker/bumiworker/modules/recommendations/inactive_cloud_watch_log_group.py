import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from bumiworker.bumiworker.modules.base import ModuleBase
from bumiworker.bumiworker.modules.pricing.aws_cloudwatch import CloudWatchLogsPricing, DEFAULT as CWL_PRICING

SUPPORTED_CLOUD_TYPES = ("aws_cnr",)

LOG = logging.getLogger(__name__)

BYTES_PER_GIB = 1024 ** 3
RECENT_WINDOW_DAYS = 30
DEFAULT_DAYS_THRESHOLD = 7


class MetricKey(str, Enum):
    INGESTION = "ingestion"
    QUERY = "query"


class InactiveCloudWatchLogGroup(ModuleBase):
    """
    Identify inactive CloudWatch Log Groups and estimate potential savings.
    """

    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = OrderedDict({
            'days_threshold': {'default': DEFAULT_DAYS_THRESHOLD},
            'excluded_pools': {
                'default': {},
                'clean_func': self.clean_excluded_pools,
            },
            'skip_cloud_accounts': {'default': []}
        })

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _parse_ts(self, ts: Any) -> Optional[datetime]:
        if ts is None:
            return None
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(float(ts), tz=timezone.utc)
            s = str(ts)
            if s.endswith("Z"):
                s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _get_from_resource(self, resource: Dict, key: str, default=None):
        """
        Get a value from the resource.
        """
        meta = resource.get('meta', {}) or {}
        if key in resource and resource.get(key) is not None:
            return resource.get(key)
        return meta.get(key, default)

    def _get_metrics(self, resource: Dict) -> Dict:
        """
        Get the metrics from the resource.
        """
        metrics = resource.get('metrics')
        if isinstance(metrics, dict):
            return metrics
        return (resource.get('meta', {}) or {}).get('metrics', {}) or {}

    def _has_recent_metrics(
            self, series: List[Dict], days_threshold: int = DEFAULT_DAYS_THRESHOLD) -> bool:
        """
        Check if the metric series has a timestamp within the recent window.
        """
        cutoff_recent_window = self._utc_now() - timedelta(days=days_threshold)
        for m in series or []:
            ts = m.get('timestamp')
            if not ts:
                continue
            try:
                t = self._parse_ts(ts)
            except Exception:
                continue

            if t >= cutoff_recent_window:
                return True
        return False

    def _sum_metrics_last_month(self, series: List[Dict]) -> float:
        """
        Sum metric values within the recent window (RECENT_WINDOW_DAYS).
        Values are assumed to be in bytes for ingestion/query metrics.
        """
        cutoff_recent_window = self._utc_now() - timedelta(days=RECENT_WINDOW_DAYS)
        total = 0
        for m in series or []:
            ts = m.get('timestamp')
            if not ts:
                continue
            try:
                t = self._parse_ts(ts)
            except Exception:
                continue
            if t >= cutoff_recent_window:
                total += m.get('value', 0) or 0
        return total

    def _is_inactive(self, resource: Dict, days_threshold: int) -> bool:
        """
        Check if the log group is inactive.
        Log group is inactive if:
            No lifecycle rules AND No recent ingestion AND No recent query
        """
        try:

            retention_days = self._get_from_resource(
                resource, 'retention_in_days')
            has_lifecycle_rules = retention_days is not None

            metrics = self._get_metrics(resource)
            ingestion_metrics = metrics.get(
                MetricKey.INGESTION.value, []) or []
            query_metrics = metrics.get(MetricKey.QUERY.value, []) or []

            has_recent_ingestion = self._has_recent_metrics(
                ingestion_metrics, days_threshold)
            has_recent_query = self._has_recent_metrics(
                query_metrics, days_threshold)

            return not (
                has_lifecycle_rules or has_recent_ingestion or has_recent_query)

        except Exception:
            return False

    def _estimate_saving(self, resource: Dict) -> float:
        """
        Calculate potential monthly savings for an inactive log group based on AWS pricing,
        without considering lifecycle policy changes.

        Uses three components:
        - Ingestion (IngestionBytes): USD 0.50 per GB (last 30 days)
        - Storage (stored_bytes): USD 0.03 per GB-month compressed (apply 0.15 compression factor)
        - Query (QueryBytes): USD 0.005 per GB scanned (last 30 days)
        """

        try:
            stored_bytes = self._get_from_resource(
                resource, 'stored_bytes', 0) or 0

            uncompressed_gb = stored_bytes / BYTES_PER_GIB
            compressed_gb = uncompressed_gb * CWL_PRICING.compression_factor
            storage_monthly_cost = compressed_gb * CWL_PRICING.storage_usd_per_gb_month

            metrics = self._get_metrics(resource)
            ingestion_metrics = metrics.get(
                MetricKey.INGESTION.value, []) or []
            query_metrics = metrics.get(MetricKey.QUERY.value, []) or []

            ingestion_bytes = self._sum_metrics_last_month(ingestion_metrics)
            query_bytes = self._sum_metrics_last_month(query_metrics)

            ingestion_gb = ingestion_bytes / BYTES_PER_GIB
            query_gb = query_bytes / BYTES_PER_GIB

            ingestion_cost = ingestion_gb * CWL_PRICING.ingestion_usd_per_gb
            query_cost = query_gb * CWL_PRICING.query_usd_per_gb

            total = storage_monthly_cost + ingestion_cost + query_cost
            return float(total)
        except Exception:
            return 0.0

    def _aggregate_resources(
            self, cloud_account_id: str) -> List[Dict[str, Any]]:
        """
        Pull log group docs for the given cloud account with only the fields we need
        for candidate selection and saving computation.
        """
        pipeline = [
            {"$match": {
                "resource_type": "Log Group",
                "cloud_account_id": cloud_account_id,
                "deleted_at": 0,
                "active": True
            }},
            {"$project": {
                "_id": 0,
                "resource_id": "$_id",
                "cloud_account_id": 1,
                "name": "$meta.name",
                "log_group_name": "$meta.name",
                "stored_bytes": "$meta.stored_bytes",
                "metrics": "$meta.metrics",
                "retention_in_days": "$meta.retention_in_days",
                "region": 1,
                "owner_id": 1,
                "pool_id": 1
            }}
        ]
        return list(self.mongo_client.restapi.resources.aggregate(pipeline))

    def _extract_cloud_account_id(self, ca: Union[str, Dict[str, Any]]) -> str:
        """
        Normalize cloud account input into its id string.
        """
        if isinstance(ca, str):
            return ca
        if isinstance(ca, dict):
            return ca.get("id") or ca.get("_id")
        return ""

    def _count_occurrences(
            self, series: List[Dict], days_threshold: int) -> int:
        """
        Count the occurrences of the metric.
        """
        cutoff_recent_window = self._utc_now() - timedelta(days=days_threshold)
        total = 0
        for m in series or []:
            ts = m.get('timestamp')
            if not ts:
                continue
            try:
                t = self._parse_ts(ts)
                if t >= cutoff_recent_window:
                    total += 1
            except Exception:
                continue
        return total

    def _get(self):
        """
        Get the inactive log groups.
        """
        (days_threshold,
         excluded_pools,
         skip_cloud_accounts) = self.get_options_values()

        ca_map = self.get_cloud_accounts(
            SUPPORTED_CLOUD_TYPES, skip_cloud_accounts)

        result: List[Dict[str, Any]] = []

        for ca in ca_map:
            ca_id = self._extract_cloud_account_id(ca)
            if not ca_id:
                LOG.warning(
                    "Skipping cloud account with unknown structure: %r", ca)
                continue
            if ca_id in skip_cloud_accounts:
                continue

            response = self._aggregate_resources(ca_id)
            for r in response:
                if r.get('pool_id') in excluded_pools:
                    is_excluded = True
                else:
                    is_excluded = False
                if not self._is_inactive(r, days_threshold):
                    continue

                saving = self._estimate_saving(r)
                ca_info = ca_map.get(r['cloud_account_id'], {})

                metrics = self._get_metrics(r)

                ingestion_occurrences = self._count_occurrences(
                    metrics.get(MetricKey.INGESTION.value, []), days_threshold)
                query_occurrences = self._count_occurrences(
                    metrics.get(MetricKey.QUERY.value, []), days_threshold)

                result.append({
                    'cloud_resource_id': r.get('resource_id'),
                    'resource_id': r.get('resource_id'),
                    'resource_name': r.get('name'),
                    'log_group_name': r.get('log_group_name'),
                    'cloud_account_id': r.get('cloud_account_id'),
                    'cloud_type': ca_info.get('type'),
                    'cloud_account_name': ca_info.get('name'),
                    'region': r.get('region'),
                    'owner': {"id": None, "name": None},
                    'pool': {"id": r.get("pool_id"), "name": None, "purpose": None},
                    'is_excluded': is_excluded,
                    'retention_in_days': r.get('retention_in_days'),
                    'stored_bytes': int(r.get('stored_bytes', 0) or 0),
                    'detected_at': self.created_at,
                    'storage': int(r.get('stored_bytes', 0) or 0),
                    'ingestion': int(ingestion_occurrences),
                    'query': int(query_occurrences),
                    'saving': saving,
                })

        return result


def main(organization_id, config_client, created_at, **kwargs):
    return InactiveCloudWatchLogGroup(
        organization_id, config_client, created_at
    ).get()


def get_module_email_name():
    return 'Inactive CloudWatch Log Groups'
