"""
Test scenarios for S3 Abandoned Buckets recommendation.

This test file covers the new implementation that checks for zero GetObject and PutObject
operations over the past 30 days to identify abandoned buckets.

Test Structure:
- Mocks MongoDB raw_expenses aggregation results
- Tests individual methods and edge cases
- Covers edge cases and boundary conditions

Note: This test file assumes the new implementation with:
- GET_OBJECT_KEY and PUT_OBJECT_KEY constants
- Updated _get_data_size_request_metrics method
- Updated get_metric_threshold_map method
- 30-day default threshold
"""

from datetime import datetime, timezone, timedelta
from typing import Callable, Dict
from unittest.mock import Mock
import copy

import pytest  # type: ignore

from bumiworker.bumiworker.modules.recommendations.s3_abandoned_buckets import (
    S3AbandonedBuckets,
    GET_OBJECT_KEY,
    PUT_OBJECT_KEY,
)


NOW_FIXED = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
START_DATE_30_DAYS = NOW_FIXED - timedelta(days=30)

# Base resource template
RESOURCE_BUCKET = {
    "_id": "bucket-resource-1",
    "cloud_account_id": "account-1",
    "cloud_resource_id": "bucket-abandoned-1",
    "name": "bucket-abandoned-1",
    "applied_rules": [],
    "created_at": 1730430000,
    "deleted_at": 0,
    "employee_id": "employee-1",
    "first_seen": 1730430000,
    "last_seen": 1761681929,
    "pool_id": "pool-1",
    "region": "us-east-1",
    "resource_type": "Bucket",
    "active": True,
    "tags": {},
}


@pytest.fixture
def module_factory(monkeypatch) -> Callable[..., S3AbandonedBuckets]:
    def _factory(
        *,
        organization_id: str = "org-1",
        created_at: int = int(NOW_FIXED.timestamp()),
        cloud_accounts: Dict = None,
    ) -> S3AbandonedBuckets:
        mod = S3AbandonedBuckets(
            organization_id=organization_id,
            config_client=Mock(),
            created_at=created_at,
        )
        monkeypatch.setattr("tools.optscale_time.utcnow", lambda: NOW_FIXED)

        if cloud_accounts is not None:
            mod.get_cloud_accounts = lambda *_args, **_kwargs: cloud_accounts
        else:
            mod.get_cloud_accounts = lambda *_args, **_kwargs: {
                "account-1": {"id": "account-1", "type": "aws_cnr", "name": "Account 1"}
            }

        return mod

    return _factory


@pytest.fixture
def mod_base(module_factory):
    """Base module with default options and placeholders."""
    mod = module_factory()
    mod.get_options = Mock(
        return_value={
            "days_threshold": 30,
            "excluded_pools": {},
            "skip_cloud_accounts": [],
        }
    )
    # Default mongo mock (tests override as needed)
    mock_mongo = Mock()
    mock_mongo.restapi.raw_expenses.aggregate = Mock(return_value=[])
    mod._mongo_client = mock_mongo

    # Default helpers
    mod.get_employees = Mock(return_value={})
    mod.get_pools = Mock(return_value={})
    mod.get_month_saving_by_daily_avg_expenses = Mock(
        return_value={"bucket-resource-1": 10.5}
    )
    return mod


class TestGetDataSizeRequestMetrics:
    """Tests for `_get_data_size_request_metrics` method."""

    def test_no_operations(self, mod_base):
        """No GetObject or PutObject operations."""
        mod = mod_base
        
        # Mock MongoDB client - only what this test needs
        mock_mongo = Mock()
        mock_mongo.restapi.raw_expenses.aggregate = Mock(return_value=[])
        mod._mongo_client = mock_mongo
        
        result = mod._get_data_size_request_metrics(
            cloud_account_id="account-1",
            cloud_resource_ids=["bucket-abandoned-1"],
            start_date=START_DATE_30_DAYS,
            days_threshold=30
        )
        
        assert "bucket-abandoned-1" in result
        assert result["bucket-abandoned-1"][GET_OBJECT_KEY] == 0
        assert result["bucket-abandoned-1"][PUT_OBJECT_KEY] == 0

    def test_getobject_only(self, mod_base):
        """GetObject operations only."""
        mod = mod_base
        raw_expenses = [
            {
                "_id": {
                    "_id": "bucket-read-only-1",
                    "operation": "GetObject"
                },
                "total_usage": 150.0
            }
        ]
        # Mock MongoDB client - only what this test needs
        mock_mongo = Mock()
        mock_mongo.restapi.raw_expenses.aggregate = Mock(return_value=raw_expenses)
        mod._mongo_client = mock_mongo
        
        result = mod._get_data_size_request_metrics(
            cloud_account_id="account-1",
            cloud_resource_ids=["bucket-read-only-1"],
            start_date=START_DATE_30_DAYS,
            days_threshold=30
        )

        assert "bucket-read-only-1" in result
        assert result["bucket-read-only-1"][GET_OBJECT_KEY] == 150
        assert result["bucket-read-only-1"][PUT_OBJECT_KEY] == 0

    def test_putobject_only(self, mod_base):
        """PutObject operations only."""
        mod = mod_base
        raw_expenses = [
            {
                "_id": {
                    "_id": "bucket-write-only-1",
                    "operation": "PutObject"
                },
                "total_usage": 150.0
            }
        ]
        # Mock MongoDB client - only what this test needs
        mock_mongo = Mock()
        mock_mongo.restapi.raw_expenses.aggregate = Mock(return_value=raw_expenses)
        mod._mongo_client = mock_mongo
        
        result = mod._get_data_size_request_metrics(
            cloud_account_id="account-1",
            cloud_resource_ids=["bucket-write-only-1"],
            start_date=START_DATE_30_DAYS,
            days_threshold=30
        )
        
        assert "bucket-write-only-1" in result
        assert result["bucket-write-only-1"][GET_OBJECT_KEY] == 0
        assert result["bucket-write-only-1"][PUT_OBJECT_KEY] == 150

    def test_putobject_and_getobject(self, mod_base):
        """PutObject and GetObject operations."""
        mod = mod_base
        raw_expenses = [
            {
                "_id": {
                    "_id": "bucket-active-only-1",
                    "operation": "PutObject"
                },
                "total_usage": 150.0
            },
            {
                "_id": {
                    "_id": "bucket-active-only-1",
                    "operation": "GetObject"
                },
                "total_usage": 100.0
            }
        ]
        # Mock MongoDB client - only what this test needs
        mock_mongo = Mock()
        mock_mongo.restapi.raw_expenses.aggregate = Mock(return_value=raw_expenses)
        mod._mongo_client = mock_mongo
        
        result = mod._get_data_size_request_metrics(
            cloud_account_id="account-1",
            cloud_resource_ids=["bucket-active-only-1"],
            start_date=START_DATE_30_DAYS,
            days_threshold=30
        )
        
        assert "bucket-active-only-1" in result
        assert result["bucket-active-only-1"][GET_OBJECT_KEY] is True
        assert result["bucket-active-only-1"][PUT_OBJECT_KEY] is True

class TestIntegration:
    """End-to-end `_get` behavior focusing on recommendation inclusion/exclusion."""

    def test_abandoned_bucket_is_recommended(self, mod_base):
        """Zero Get/Put -> abandoned -> recommended (saving > 0)."""
        mod = mod_base
        # No operations
        mod._mongo_client.restapi.raw_expenses.aggregate = Mock(return_value=[])
        # Active bucket
        bucket = copy.deepcopy(RESOURCE_BUCKET)
        bucket["cloud_resource_id"] = "bucket-abandoned-1"
        mod.get_active_resources = Mock(return_value={"account-1": [bucket]})

        result = mod._get()

        assert len(result) == 1
        assert result[0]["cloud_resource_id"] == "bucket-abandoned-1"
        assert result[0]["get_object_count"] is False
        assert result[0]["put_object_count"] is False
        assert result[0]["saving"] == 10.5

    def test_active_bucket_not_recommended(self, mod_base):
        """Any Get/Put > 0 -> not abandoned -> not recommended."""
        mod = mod_base
        raw_expenses = [
            {
                "_id": {"_id": "bucket-active-1", "operation": "GetObject"},
                "total_usage": 10.0,
            }
        ]
        mod._mongo_client.restapi.raw_expenses.aggregate = Mock(return_value=raw_expenses)

        bucket = copy.deepcopy(RESOURCE_BUCKET)
        bucket["cloud_resource_id"] = "bucket-active-1"
        mod.get_active_resources = Mock(return_value={"account-1": [bucket]})

        result = mod._get()

        assert len(result) == 0

    def test_zero_saving_not_recommended(self, mod_base):
        """Zero ops but zero saving -> skip recommendation."""
        mod = mod_base
        mod._mongo_client.restapi.raw_expenses.aggregate = Mock(return_value=[])
        mod.get_month_saving_by_daily_avg_expenses = Mock(return_value={"bucket-resource-1": 0})

        bucket = copy.deepcopy(RESOURCE_BUCKET)
        bucket["cloud_resource_id"] = "bucket-abandoned-1"
        mod.get_active_resources = Mock(return_value={"account-1": [bucket]})

        result = mod._get()

        assert len(result) == 0

    def test_operations_not_get_or_put_object_are_recommended(self, mod_base):
        """Any operations not GetObject or PutObject are recommended."""
        mod = mod_base
        raw_expenses = [
            {
                "_id": {"_id": "bucket-active-list-operations-1", "operation": "ListObjects"},
                "total_usage": 10.0,
            }
        ]
        mod._mongo_client.restapi.raw_expenses.aggregate = Mock(return_value=raw_expenses)

        bucket = copy.deepcopy(RESOURCE_BUCKET)
        bucket["cloud_resource_id"] = "bucket-active-list-operations-1"
        mod.get_active_resources = Mock(return_value={"account-1": [bucket]})

        result = mod._get()

        assert len(result) == 1
        assert result[0]["cloud_resource_id"] == "bucket-active-list-operations-1"
        assert result[0]["get_object_count"] is False
        assert result[0]["put_object_count"] is False
        assert result[0]["saving"] == 10.5

        
