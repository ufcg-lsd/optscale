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

import pytest  # type: ignore

from bumiworker.bumiworker.modules.recommendations.s3_abandoned_buckets import (
    S3AbandonedBuckets,
    GET_OBJECT_KEY,
    PUT_OBJECT_KEY,
)


NOW_FIXED = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
START_DATE_30_DAYS = NOW_FIXED - timedelta(days=30)


@pytest.fixture
def module_factory(monkeypatch) -> Callable[[], S3AbandonedBuckets]:
    """
    Factory for module instances with frozen `now` and basic dependencies.

    Adjust as needed per test scenario.
    """

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

        return mod

    return _factory


@pytest.fixture
def mod_base(module_factory):
    """Basic module with default options."""
    mod = module_factory()
    mod.get_options = Mock(return_value={
        'days_threshold': 30,
        'excluded_pools': {},
        'skip_cloud_accounts': []
    })
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
        
        assert result["bucket-read-only-1"][GET_OBJECT_KEY] == 150
        assert result["bucket-read-only-1"][PUT_OBJECT_KEY] == 0

    def test_putobject_only(self, mod_base):
        """GetObject operations only."""
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
        
        assert result["bucket-active-only-1"][GET_OBJECT_KEY] == 100
        assert result["bucket-active-only-1"][PUT_OBJECT_KEY] == 150