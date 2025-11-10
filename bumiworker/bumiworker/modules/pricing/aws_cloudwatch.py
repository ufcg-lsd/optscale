"""
Pricing for AWS CloudWatch Logs
See: https://aws.amazon.com/cloudwatch/pricing/ (values may vary by region)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CloudWatchLogsPricing:
    storage_usd_per_gb_month: float
    ingestion_usd_per_gb: float
    query_usd_per_gb: float
    compression_factor: float


# from us-east-1
DEFAULT = CloudWatchLogsPricing(
    storage_usd_per_gb_month=0.03,
    ingestion_usd_per_gb=0.50,
    query_usd_per_gb=0.005,
    compression_factor=0.15,
)