from bumiworker.bumiworker.modules.abandoned_base import (
    S3AbandonedBucketsArchiveBase
)
from bumiworker.bumiworker.modules.recommendations.s3_abandoned_buckets import (
    S3AbandonedBuckets as S3AbandonedBucketsRecommendation,
    GET_OBJECT_KEY, PUT_OBJECT_KEY
)


class S3AbandonedBuckets(S3AbandonedBucketsArchiveBase,
                         S3AbandonedBucketsRecommendation):
    SUPPORTED_CLOUD_TYPES = [
        'aws_cnr'
    ]

    def get_previous_metric_threshold_map(self, previous_options):
        # Buckets are considered abandoned if both GetObject and PutObject
        # operations are zero (no read or write activity)
        # For backward compatibility, if old options exist, we still use
        # the new logic since the recommendation criteria has changed
        return {
            GET_OBJECT_KEY: 0,
            PUT_OBJECT_KEY: 0
        }


def main(organization_id, config_client, created_at, **kwargs):
    return S3AbandonedBuckets(
        organization_id, config_client, created_at).get()
