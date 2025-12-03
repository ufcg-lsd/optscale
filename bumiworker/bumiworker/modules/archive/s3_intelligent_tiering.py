from typing import Dict
from bumiworker.bumiworker.consts import ArchiveReason
from bumiworker.bumiworker.modules.base import ArchiveBase
from bumiworker.bumiworker.modules.recommendations.constants import (
    IT_POSITIVE_STATUS,
)
from bumiworker.bumiworker.modules.recommendations.s3_intelligent_tiering import (
    S3IntelligentTiering as S3IntelligentTieringRecommendation,
)


class S3IntelligentTiering(ArchiveBase, S3IntelligentTieringRecommendation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reason_description_map[
            ArchiveReason.RECOMMENDATION_APPLIED
        ] = "intelligent-tiering enabled"
        self.reason_description_map[
            ArchiveReason.RECOMMENDATION_IRRELEVANT
        ] = "bucket no longer matches intelligent-tiering criteria"

    @property
    def supported_cloud_types(self):
        return list(self.SUPPORTED_CLOUD_TYPES)

    def _is_it_enabled(self, doc: Dict) -> bool:
        status = doc.get("it_status_bucket")
        if status is None:
            status = (doc.get("meta") or {}).get("it_status_bucket")
        if status is None:
            return False
        return str(status).lower() in IT_POSITIVE_STATUS

    def _get(self, previous_options, optimizations, cloud_accounts_map, **kwargs):
        current_options = self.get_options()
        current_excluded_pools = set(
            (current_options.get("excluded_pools") or {}).keys()
        )
        current_skip_accounts = set(
            current_options.get("skip_cloud_accounts") or []
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
            account_docs = docs_cache.get(cloud_account_id)
            if account_docs is None:
                docs = self._aggregate_resources(cloud_account_id)
                account_docs = {doc["resource_id"]: doc for doc in docs}
                docs_cache[cloud_account_id] = account_docs
            bucket_doc = account_docs.get(optimization["resource_id"])
            if not bucket_doc:
                resource = resources_collection.find_one(
                    {"_id": optimization["resource_id"]}
                )
                if resource and self._is_it_enabled(resource):
                    reason = ArchiveReason.RECOMMENDATION_APPLIED
                elif resource:
                    reason = ArchiveReason.RESOURCE_DELETED
                else:
                    reason = ArchiveReason.RESOURCE_DELETED
                self._set_reason_properties(optimization, reason)
                result.append(optimization)
                continue
            if bucket_doc.get("pool_id") in current_excluded_pools:
                self._set_reason_properties(
                    optimization, ArchiveReason.OPTIONS_CHANGED
                )
                result.append(optimization)
                continue
            if self._is_it_enabled(bucket_doc):
                reason = ArchiveReason.RECOMMENDATION_APPLIED
            else:
                eval_res = self._candidate_and_saving(bucket_doc)
                if eval_res.get("is_candidate"):
                    reason = ArchiveReason.OPTIONS_CHANGED
                else:
                    reason = ArchiveReason.RECOMMENDATION_IRRELEVANT
            self._set_reason_properties(optimization, reason)
            result.append(optimization)
        return result


def main(organization_id, config_client, created_at, **kwargs):
    return S3IntelligentTiering(
        organization_id, config_client, created_at
    ).get()
