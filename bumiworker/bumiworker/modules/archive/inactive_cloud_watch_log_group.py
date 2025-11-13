from typing import Dict

from bumiworker.bumiworker.consts import ArchiveReason
from bumiworker.bumiworker.modules.base import ArchiveBase
from bumiworker.bumiworker.modules.recommendations.inactive_cloud_watch_log_group import (
    InactiveCloudWatchLogGroup as InactiveCloudWatchLogGroupRecommendation,
    DEAD_RESOURCE_DAYS_DEFAULT,
    SUPPORTED_CLOUD_TYPES,
)


class InactiveCloudWatchLogGroup(ArchiveBase, InactiveCloudWatchLogGroupRecommendation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reason_description_map[
            ArchiveReason.RECOMMENDATION_APPLIED
        ] = "log group removed or deactivated"
        self.reason_description_map[
            ArchiveReason.RECOMMENDATION_IRRELEVANT
        ] = "log group has recent activity"

    @property
    def supported_cloud_types(self):
        return SUPPORTED_CLOUD_TYPES

    def _get_pool_id(self, optimization: Dict) -> str:
        pool = optimization.get("pool")
        if isinstance(pool, dict):
            pool_id = pool.get("id")
            if pool_id:
                return pool_id
        return optimization.get("pool_id")

    def _get(self, previous_options, optimizations, cloud_accounts_map, **kwargs):
        current_options = self.get_options()
        current_dead_resource_days = current_options.get(
            "dead_resource_days",
            current_options.get("days_threshold", DEAD_RESOURCE_DAYS_DEFAULT),
        )
        current_excluded_pools = set((current_options.get("excluded_pools") or {}).keys())
        current_skip_accounts = set(current_options.get("skip_cloud_accounts") or [])

        previous_dead_resource_days = previous_options.get(
            "dead_resource_days",
            previous_options.get("days_threshold", DEAD_RESOURCE_DAYS_DEFAULT),
        )

        docs_cache: Dict[str, Dict[str, Dict]] = {}
        resources_collection = self.mongo_client.restapi.resources

        result = []
        for optimization in optimizations:
            cloud_account_id = optimization["cloud_account_id"]

            if cloud_account_id not in cloud_accounts_map:
                self._set_reason_properties(
                    optimization, ArchiveReason.CLOUD_ACCOUNT_DELETED
                )
                result.append(optimization)
                continue

            if cloud_account_id in current_skip_accounts:
                self._set_reason_properties(
                    optimization, ArchiveReason.OPTIONS_CHANGED
                )
                result.append(optimization)
                continue

            pool_id = self._get_pool_id(optimization)
            if pool_id in current_excluded_pools:
                self._set_reason_properties(
                    optimization, ArchiveReason.OPTIONS_CHANGED
                )
                result.append(optimization)
                continue

            account_docs = docs_cache.get(cloud_account_id)
            if account_docs is None:
                docs = self._aggregate_resources(cloud_account_id)
                account_docs = {doc["resource_id"]: doc for doc in docs}
                docs_cache[cloud_account_id] = account_docs

            log_group_doc = account_docs.get(optimization["resource_id"])
            if not log_group_doc:
                resource = resources_collection.find_one(
                    {"_id": optimization["resource_id"]}
                )
                if not resource or resource.get("deleted_at") or not resource.get("active", True):
                    reason = ArchiveReason.RECOMMENDATION_APPLIED
                else:
                    reason = ArchiveReason.RECOMMENDATION_IRRELEVANT
                self._set_reason_properties(optimization, reason)
                result.append(optimization)
                continue

            inactive_with_previous_threshold = self._is_inactive(
                log_group_doc, previous_dead_resource_days
            )
            inactive_with_current_threshold = self._is_inactive(
                log_group_doc, current_dead_resource_days
            )

            if not inactive_with_previous_threshold:
                reason = ArchiveReason.RECOMMENDATION_IRRELEVANT
            elif not inactive_with_current_threshold:
                if current_dead_resource_days != previous_dead_resource_days:
                    reason = ArchiveReason.OPTIONS_CHANGED
                else:
                    reason = ArchiveReason.RECOMMENDATION_IRRELEVANT
            else:
                reason = ArchiveReason.OPTIONS_CHANGED

            self._set_reason_properties(optimization, reason)
            result.append(optimization)
        return result


def main(organization_id, config_client, created_at, **kwargs):
    return InactiveCloudWatchLogGroup(
        organization_id, config_client, created_at
    ).get()
