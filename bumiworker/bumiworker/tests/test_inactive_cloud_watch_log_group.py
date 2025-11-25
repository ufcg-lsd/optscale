from datetime import datetime, timezone
from typing import Callable, Dict
from unittest.mock import Mock
import copy

import pytest  # type: ignore

from bumiworker.modules.recommendations.inactive_cloud_watch_log_group import (
    InactiveCloudWatchLogGroup,
    MetricKey,
)


NOW_FIXED = datetime(2025, 11, 7, 0, 0, 0, tzinfo=timezone.utc)

# Base resource template for tests
RESOURCE_LOG_GROUP = {
    "_id": "1",
    "cloud_account_id": "account_1",
    "cloud_resource_id": "resource_1",
    "applied_rules": [],
    "created_at": 1730430000,
    "deleted_at": 0,
    "employee_id": "employee_1",
    "first_seen": 1730430000,
    "last_seen": 1761681929,
    "meta": {
        "name": "name_1",
        "stored_bytes": 0,
        "creation_time": "2020-09-01T18:26:08.993000+00:00",
        "arn": "arn_1",
        "metrics": {
            "ingestion": [],
            "storage": [],
            "incoming_events": [],
            "query": []
        }
    },
    "pool_id": "pool_1",
    "region": "us-east-1",
    "resource_type": "Log Group",
    "tags": {}
}


@pytest.fixture
def module_factory(monkeypatch) -> Callable[[], InactiveCloudWatchLogGroup]:
    """
    Factory for module instances with frozen `now` and basic dependencies.

    Adjust as needed per test scenario.
    """

    def _factory(
        *,
        organization_id: str = "org-1",
        created_at: int = int(NOW_FIXED.timestamp()),
        cloud_accounts: Dict = None,
    ) -> InactiveCloudWatchLogGroup:
        mod = InactiveCloudWatchLogGroup(
            organization_id=organization_id,
            config_client=Mock(),
            created_at=created_at,
        )
        monkeypatch.setattr(mod, "_utc_now", lambda: NOW_FIXED)

        if cloud_accounts is not None:
            mod.get_cloud_accounts = lambda *_args, **_kwargs: cloud_accounts

        return mod

    return _factory

@pytest.fixture
def mod_base(module_factory):
    """ Basic module with default options."""
    mod = module_factory()
    mod.get_options_values = Mock(return_value=(7, set(), set()))
    return mod

#
# Note: No module-level skip to allow running implemented tests (e.g., TC-06).

class TestHasRecentMetrics:
    """Tests for `_has_recent_metrics` method."""

    def test_no_metrics(self, module_factory):
        """No metrics."""
        mod = module_factory()
        series = []
        assert mod._has_recent_metrics(series, days_threshold=7) is False
        assert mod._count_occurrences_in_threshold(series, days_threshold=7) == 0

    def test_metrics_outside_threshold(self, module_factory):
        """Metrics outside the threshold."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-10-21T12:15:00+00:00",
                "value" : 2000
        },
        {
                "timestamp" : "2025-10-07T12:35:00+00:00",
                "value" : 1000
        } ]
        assert mod._has_recent_metrics(series, days_threshold=7) is False
    
    def test_metrics_within_threshold(self, module_factory):
        """Metrics within the threshold."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-11-04T22:01:00+00:00",
                "value" : 500
        },
        {
                "timestamp" : "2025-11-01T16:05:00+00:00",
                "value" : 2500
        } ]
        assert mod._has_recent_metrics(series, days_threshold=7) is True

    def test_metrics_exact_threshold(self, module_factory):
        """Metrics exactly on the threshold edge."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T12:00:00+00:00",
            "value" : 2500
        } ]
        assert mod._has_recent_metrics(series, days_threshold=7) is True

class TestCountOccurrencesInThreshold:
    """Tests for `_count_occurrences_in_threshold` method."""

    def test_missing_timestamp(self, module_factory):
        """Metric entry missing 'timestamp' key."""
        mod = module_factory()
        series = [{"value": 123}]
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 0

    def test_no_metrics(self, module_factory):
        """No metrics."""
        mod = module_factory()
        series = []
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 0

    def test_metrics_within_threshold_7_days(self, module_factory):
        """Metrics within 7 days."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:01:00+00:00",
            "value" : 500
        } ]
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 1
    
    def test_metrics_within_threshold_30_days(self, module_factory):
        """Metrics within 30 days."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-10-21T12:15:00+00:00",
                "value" : 2000
        },
        {
                "timestamp" : "2025-10-08T12:35:00+00:00",
                "value" : 1000
        } ]
        count = mod._count_occurrences_in_threshold(series, days_threshold=30)
        assert count == 2

    def test_metrics_within_and_outside_threshold(self, module_factory):
        """Metrics both within and outside the 7-day threshold."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-11-04T22:01:00+00:00",
                "value" : 500
        },
        {
                "timestamp" : "2025-10-21T12:15:00+00:00",
                "value" : 2000
        },
        {
                "timestamp" : "2025-10-08T12:35:00+00:00",
                "value" : 1000
        } ]
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 1

class TestSumMetricsLastMonth:
    """Tests for `_sum_metrics_last_month` method."""

    def test_no_metrics(self, module_factory):
        """No metrics."""
        mod = module_factory()
        series = []
        sum = mod._sum_metrics_last_month(series)
        assert sum == 0

    def test_metrics_within_7_days(self, module_factory):
        """Metrics within 7 days."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:22:01+00:00",
            "value" : 500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 500

    def test_metrics_within_30_days(self, module_factory):
        """Metrics within 30 days."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T00:00:00+00:00",
            "value" : 3000
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 3000

    def test_metrics_exact_30_days(self, module_factory):
        """Metrics exactly 30 days ago."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-10-08T00:00:00+00:00",
            "value" : 1500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 1500

    def test_metrics_outside_threshold(self, module_factory):
        """Metrics outside the 30-day threshold."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-08-07T08:15:00+00:00",
                "value" : 1000
        },
        {
                "timestamp" : "2025-08-07T00:00:00+00:00",
                "value" : 1500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 0

    def test_metrics_within_and_outside_threshold(self, module_factory):
        """Metrics both within and outside the 30-day threshold."""
        mod = module_factory()
        series= [ {
                "timestamp" : "2025-11-04T22:01:00+00:00",
                "value" : 500
        },
        {
                "timestamp" : "2025-11-01T16:05:00+00:00",
                "value" : 2500
        },
        {
            "timestamp" : "2025-11-01T00:00:00+00:00",
                "value" : 3000
        },
        {
                "timestamp" : "2025-10-21T12:15:00+00:00",
                "value" : 2000
        },
        {
                "timestamp" : "2025-10-08T12:35:00+00:00",
                "value" : 1000
        },
        {
                "timestamp" : "2025-10-08T00:00:00+00:00",
                "value" : 1500
        },
        {
                "timestamp" : "2025-08-07T08:15:00+00:00",
                "value" : 1000
        },
        {
                "timestamp" : "2025-08-07T00:00:00+00:00",
                "value" : 1500
        }]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 10500

class TestInactivity:
    """Tests for `_is_inactive` method."""

    def test_empty_resource(self, module_factory):
        """No lifecycle and no metrics."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        assert mod._is_inactive(resource, 7) is True

    def test_has_lifecycle(self, module_factory):
        """Has retention policy."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["retention_in_days"] = 3
        assert mod._is_inactive(resource, 7) is False

    def test_recent_ingestion(self, module_factory):
        """Ingestion metrics in the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-11-04T22:01:00+00:00",
          "value" : 500
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_ingestion_exact_threshold(self, module_factory):
        """Ingestion metrics on the threshold edge."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-10-31T00:00:00+00:00",
          "value" : 2500
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_ingestion_outside_threshold(self, module_factory):
        """Ingestion metrics outside the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
        "timestamp" : "2025-10-21T12:15:00+00:00",
        "value" : 2000
        },
        {
        "timestamp" : "2025-10-07T12:35:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is True

    def test_ingestion_inside_and_outside_threshold(self, module_factory):
        """Ingestion metrics both inside and outside the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-11-04T22:01:00+00:00",
          "value" : 500
        },
        {
        "timestamp" : "2025-10-07T12:35:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_recent_query(self, module_factory):
        """Query metrics in the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-11-04T18:30:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_query_exact_threshold(self, module_factory):
        """Query metrics on the threshold edge."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-31T00:00:00+00:00",
        "value" : 2000
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_query_outside_threshold(self, module_factory):
        """Query metrics outside the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-23T15:25:00+00:00",
        "value" : 2500
        },
        {
        "timestamp" : "2025-10-07T13:35:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is True

    def test_query_inside_and_outside_threshold(self, module_factory):
        """Query metrics both inside and outside the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-11-04T18:30:00+00:00",
        "value" : 1000
        },
        {
        "timestamp" : "2025-10-07T13:35:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_recent_query_and_ingestion(self, module_factory):
        """Both query and ingestion metrics in the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-11-04T22:01:00+00:00",
          "value" : 500
        }]
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-31T17:55:00+00:00",
        "value" : 1500
        }]
        assert mod._is_inactive(resource, 7) is False

    def test_querry_and_ingestion_outside_threshold(self, module_factory):
        """Both query and ingestion metrics outside the threshold."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
        "timestamp" : "2025-10-21T12:15:00+00:00",
        "value" : 2000
        },
        {
        "timestamp" : "2025-10-07T12:35:00+00:00",
        "value" : 1000
        }]
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-23T15:25:00+00:00",
        "value" : 2500
        },
        {
        "timestamp" : "2025-10-07T13:35:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, 7) is True

class TestSaving:
    """Tests for `_estimate_saving` method."""

    def test_no_metrics(self, module_factory):
        """No metrics or storage."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        
        saving = mod._estimate_saving(resource)
        assert saving == 0

    def test_ingestion_last_month(self, module_factory):
        """Ingestion metrics in the last month."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [ {
            "timestamp" : "2025-10-21T12:15:00+00:00",
            "value" : 2000
        } ]
        saving = mod._estimate_saving(resource)
        assert saving == pytest.approx(9.31e-07, rel=1e-3)
    
    def test_query_last_month(self, module_factory):
        """Query metrics in the last month."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-23T15:25:00+00:00",
        "value" : 2500
        }]
        saving = mod._estimate_saving(resource)
        assert saving == pytest.approx(1.12e-08, rel=5e-2)

    def test_storage_only(self, module_factory):
        """Storage metrics only."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["stored_bytes"] = 3 * 1024 * 1024 * 1024  # 3 GiB
        saving = mod._estimate_saving(resource)
        assert saving == pytest.approx(0.0135, rel=1e-3)

    def test_query_and_ingestion_and_storage(self, module_factory):
        """Storage, ingestion and query metrics."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["stored_bytes"] = 3 * 1024 * 1024 * 1024  # 3 GiB
        resource["meta"]["metrics"]["ingestion"] = [ {
        "timestamp" : "2025-10-21T12:15:00+00:00",
        "value" : 2000
        }]
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-23T15:25:00+00:00",
        "value" : 2500
        }]
        saving = mod._estimate_saving(resource)

        assert saving == pytest.approx(0.013500943, rel=1e-3)

    def test_ingestion_not_recently(self, module_factory):
        """Ingestion metrics not recent."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
        "timestamp" : "2025-08-07T08:15:00+00:00",
        "value" : 1000
    }]
        saving = mod._estimate_saving(resource)
        assert saving == 0

    def test_query_not_recently(self, module_factory):
        """Query metrics not recent."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-08-07T15:15:00+00:00",
        "value" : 500
    }]
        saving = mod._estimate_saving(resource)
        assert saving == 0

class TestIntegration:
    """Tests for the `_get` method."""

    def test__basic_resource(self, mod_base):
        """Basic resource aggregation test."""
        mod = mod_base

        ca_map = {"acc1": {"id": "acc1", "type": "aws", "name": "Account 1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value=([{
            "resource_id": "r1",
            "name": "log-group-1",
            "cloud_account_id": "acc1",
            "log_group_name": "group1",
            "region": "us-east-1",
            "pool_id": "p1",
            "stored_bytes": 12345,
            "retention_in_days": 7,
        }]))
        mod._is_inactive = Mock(return_value=True)
        mod._estimate_saving = Mock(return_value=0.5)
        mod._get_metrics = Mock(return_value={
            MetricKey.INGESTION.value: [],
            MetricKey.QUERY.value: [],
        })
        mod._count_occurrences_in_threshold = Mock(return_value=2)

        result = mod._get()

        assert len(result) == 1
        item = result[0]
        assert item["cloud_account_id"] == "acc1"
        assert item["resource_id"] == "r1"
        assert item["saving"] == 0.5
        assert item["is_excluded"] is False
        assert item["ingestion"] == 2
        assert item["query"] == 2
        assert item["cloud_account_name"] == "Account 1"
        assert item["cloud_type"] == "aws"

    def test_filter_excluded_pools(self, mod_base):
        """Filters out resources in excluded pools."""
        mod = mod_base
        excluded_pool = "pool_excl"
        mod.get_options_values = Mock(return_value=(7, {excluded_pool}, set()))
        ca_map = {"acc1": {"id": "acc1", "type": "aws", "name": "Account 1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value = ([
            {"resource_id": "r1", "cloud_account_id": "acc1", "pool_id": excluded_pool}
        ]))
        mod._is_inactive = Mock(return_value=True)
        mod._estimate_saving = Mock(return_value=0)
        mod._get_metrics = Mock(return_value={MetricKey.INGESTION.value: [], MetricKey.QUERY.value: []})
        mod._count_occurrences_in_threshold = Mock(return_value=0)

        result = mod._get()
        assert result[0]["is_excluded"] is True

    def test_skip_cloud_accounts(self, mod_base):
        """"Skips cloud accounts in `skip_cloud_accounts`."""
        mod = mod_base
        mod.get_options_values = Mock(return_value=(7, set(), {"acc1"}))
        ca_map = {"acc1": {"id": "acc1", "type": "aws", "name": "Account 1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value = ([]))
        result = mod._get()
        assert result == []

    def test_aggregated_metrics(self, mod_base):
        """Verify that aggregated metrics are reflected in the final result."""
        mod = mod_base
        ca_map = {"acc1": {"id": "acc1", "type": "aws", "name": "Account 1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value = ([
            {"resource_id": "r1", "cloud_account_id": "acc1", "pool_id": "p1"},
        ]))
        mod._is_inactive = Mock(return_value=True)
        mod._estimate_saving = Mock(return_value=0.42)
        mod._get_metrics = Mock(return_value={
            MetricKey.INGESTION.value: [{"timestamp": "2025-11-04T00:00:00+00:00"}],
            MetricKey.QUERY.value: [{"timestamp": "2025-11-03T00:00:00+00:00"}],
        })
        mod._count_occurrences_in_threshold = Mock(side_effect=[3, 5])

        result = mod._get()
        assert result[0]["ingestion"] == 3
        assert result[0]["query"] == 5
        assert result[0]["saving"] == 0.42

    def test_aggregate_resources_projection(self, mod_base):
        """Verify that `_aggregate_resources` is called correctly."""
        mod = mod_base
        ca_map = {"acc1": {"id": "acc1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value = ([]))
        mod._is_inactive = Mock(return_value=False)

        result = mod._get()

        mod._aggregate_resources.assert_called_once_with("acc1")
        assert result == []


# Enum used in many scenarios — imported here to avoid unused symbol lint.
_ = MetricKey


