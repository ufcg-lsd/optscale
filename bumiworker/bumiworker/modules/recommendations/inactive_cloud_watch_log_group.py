import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
from bumiworker.bumiworker.modules.base import ModuleBase
from bumiworker.bumiworker.modules.pricing.aws_cloudwatch import CloudWatchLogsPricing, DEFAULT as CWL_PRICING

SUPPORTED_CLOUD_TYPES = ("aws_cnr",)

LOG = logging.getLogger(__name__)

BYTES_PER_GIB = 1024 ** 3  
RECENT_WINDOW_DAYS_DEFAULT = 30
DEAD_RESOURCE_DAYS_DEFAULT = 30
MIN_STORAGE_BYTES_DEFAULT = 1 * 1024 * 1024 

class MetricKey(str, Enum):
    INGESTION = "IngestionBytes"
    EVENTS = "IncomingLogEvents"
    QUERY = "QueryBytes"


class InactiveCloudWatchLogGroup(ModuleBase):
    """
    Identify inactive CloudWatch Log Groups and estimate potential savings.
    """
    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = OrderedDict({
            'dead_resource_days': {'default': DEAD_RESOURCE_DAYS_DEFAULT},
            'min_storage_bytes': {'default': MIN_STORAGE_BYTES_DEFAULT},
            'excluded_pools': {
                'default': {},
                'clean_func': self.clean_excluded_pools,
            },
            'skip_cloud_accounts': {'default': []}
        })

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

    def _sum_metrics_recent_window(self, series: List[Dict]) -> float:
        """
        Sum metric values within the recent window (RECENT_WINDOW_DAYS).
        Values are assumed to be in bytes for ingestion/query metrics.
        """
        cutoff_recent_window = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS_DEFAULT)
        total = 0
        for m in series or []:
            ts = m.get('timestamp')
            if not ts:
                continue
            try:
                t = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
            except Exception:
                continue
            if t >= cutoff_recent_window:
                total += m.get('value', 0) or 0
        return total

    def _is_inactive(self, resource: Dict, dead_resource_days: int) -> bool:
        """
        Check if the log group is inactive.

        Log group is inactive if:
            - No lifecycle rules AND 
            - No recent ingestion, OR
            - Dead resource detected
        """
        try:
            retention_days = self._get_from_resource(resource, 'retention_in_days')
            has_lifecycle_rules = retention_days is not None

            last_collected_at = self._get_from_resource(resource, 'last_collected_at')

            is_dead_resource = False
            if last_collected_at:
                try:
                    if isinstance(last_collected_at, (int, float)):
                        last_collection = datetime.utcfromtimestamp(last_collected_at)
                    else:
                        last_collection = datetime.fromisoformat(
                            str(last_collected_at).replace('Z', '+00:00')
                        )
                    is_dead_resource = (datetime.utcnow() - last_collection).days > dead_resource_days
                except Exception:
                    pass

            metrics = self._get_metrics(resource)
            ingestion_metrics = metrics.get('IngestionBytes', []) or []
            incoming_events = metrics.get('IncomingLogEvents', []) or []

            recent_ingestion = self._sum_metrics_recent_window(ingestion_metrics)
            recent_events = self._sum_metrics_recent_window(incoming_events)
            no_recent_ingestion = (recent_ingestion == 0 and recent_events == 0)

            return (not has_lifecycle_rules and (no_recent_ingestion or is_dead_resource))

        except Exception:
            return False

    def _estimate_saving(self, resource: Dict) -> float:

        """
        Calculate potential monthly savings for an inactive log group based on AWS pricing,
        without considering lifecycle policy changes.
        
        Uses three components:
        - Ingestion (IncomingBytes): USD 0.50 per GB (last 30 days)
        - Storage (stored_bytes): USD 0.03 per GB-month compressed (apply 0.15 compression factor)
        - Query (QueryBytes): USD 0.005 per GB scanned (last 30 days)
        """
        
        try:
            stored_bytes = self._get_from_resource(resource, 'stored_bytes', 0) or 0

            uncompressed_gb = stored_bytes / BYTES_PER_GIB
            compressed_gb = uncompressed_gb * CWL_PRICING.compression_factor
            storage_monthly_cost = compressed_gb * CWL_PRICING.storage_usd_per_gb_month

            metrics = self._get_metrics(resource)
            ingestion_metrics = metrics.get('IngestionBytes', []) or []
            query_metrics = metrics.get('QueryBytes', []) or []

            ingestion_bytes = self._sum_metrics_recent_window(ingestion_metrics)
            query_bytes = self._sum_metrics_recent_window(query_metrics)

            ingestion_gb = ingestion_bytes / BYTES_PER_GIB
            query_gb = query_bytes / BYTES_PER_GIB

            ingestion_cost = ingestion_gb * CWL_PRICING.ingestion_usd_per_gb
            query_cost = query_gb * CWL_PRICING.query_usd_per_gb

            total = storage_monthly_cost + ingestion_cost + query_cost
            return round(total, 2)
        except Exception:
            return 0.0
    
            

    def _get(self):
        """
        Get the inactive log groups.
        """
        (dead_resource_days, min_storage_bytes,
         excluded_pools, skip_cloud_accounts) = self.get_options_values()

        ca_map = self.get_cloud_accounts(SUPPORTED_CLOUD_TYPES, skip_cloud_accounts)
        _, response = self.rest_client.cloud_resources_discover(
            self.organization_id, 'log_group')

        employees = self.get_employees()
        pools = self.get_pools()

        result = []
        for r in response['data']:
            if r.get('cloud_account_id') not in ca_map:
                continue

            if r.get('pool_id') in excluded_pools:
                is_excluded = True
            else:
                is_excluded = False

            if not self._is_inactive(r, dead_resource_days):
                continue

            saving = self._estimate_saving(r, min_storage_bytes)
            ca_info = ca_map.get(r['cloud_account_id'], {})

            metrics = self._get_metrics(r)
            ingestion_bytes_30d = self._sum_metrics_recent_window(metrics.get('IngestionBytes', []))
            query_bytes_30d = self._sum_metrics_recent_window(metrics.get('QueryBytes', []))

            result.append({
                'cloud_resource_id': r.get('cloud_resource_id'),
                'resource_name': r.get('name'),
                'log_group_name': r.get('name'),
                'resource_id': r.get('resource_id'),
                'cloud_account_id': r.get('cloud_account_id'),
                'cloud_type': ca_info.get('type'),
                'cloud_account_name': ca_info.get('name'),
                'region': r.get('region') or self._get_from_resource(r, 'region'),
                'owner': self._extract_owner(r.get('owner_id'), employees),
                'pool': self._extract_pool(r.get('pool_id'), pools),
                'is_excluded': is_excluded,
                'retention_in_days': self._get_from_resource(r, 'retention_in_days'),
                'stored_bytes': self._get_from_resource(r, 'stored_bytes', 0) or 0,
                'storage': self._get_from_resource(r, 'stored_bytes', 0) or 0,
                'ingestion': ingestion_bytes_30d,
                'query': query_bytes_30d,
                'saving': saving,
            })

        return result


def main(organization_id, config_client, created_at, **kwargs):
    return InactiveCloudWatchLogGroup(
        organization_id, config_client, created_at
    ).get()


def get_module_email_name():
    return 'Inactive CloudWatch Log Groups'