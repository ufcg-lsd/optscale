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

# Common thresholds used by tests (7 days and 30 days)
THRESHOLD_WEEK = 7
THRESHOLD_MONTH = 30

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

    The factory freezes the module's current time (`_utc_now`) to
    `NOW_FIXED` so tests are deterministic.
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
    """
    Basic module instance with default configuration.
    Returns a module with a 7-day threshold and no exclusions.
    """

    mod = module_factory()
    mod.get_options_values = Mock(return_value=(THRESHOLD_WEEK, set(), set()))
    return mod

class TestHasRecentMetrics:
    """Tests for the `_has_recent_metrics` helper.

    These verify edge cases: no metrics, metrics outside/inside the
    threshold and metrics exactly on the threshold boundary.
    """

    def test_no_metrics(self, module_factory):
        """Return False when the metric series is empty."""
        mod = module_factory()
        series = []
        assert mod._has_recent_metrics(series, days_threshold=THRESHOLD_WEEK) is False
        assert mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK) == 0

    def test_metrics_outside_threshold(self, module_factory):
        """Metrics older than the threshold should not be counted."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-10-21T12:15:00+00:00",
                "value" : 2000
        },
        {
                "timestamp" : "2025-10-07T12:35:00+00:00",
                "value" : 1000
        } ]
        assert mod._has_recent_metrics(series, days_threshold=THRESHOLD_WEEK) is False
    
    def test_metrics_within_threshold(self, module_factory):
        """Recent metrics within the threshold return True."""
        mod = module_factory()
        series= [{
                "timestamp" : "2025-11-04T22:01:00+00:00",
                "value" : 500
        },
        {
                "timestamp" : "2025-11-01T16:05:00+00:00",
                "value" : 2500
        } ]
        assert mod._has_recent_metrics(series, days_threshold=THRESHOLD_WEEK) is True

    def test_metrics_exact_threshold(self, module_factory):
        """A metric on the threshold boundary is treated as recent."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T12:00:00+00:00",
            "value" : 2500
        } ]
        assert mod._has_recent_metrics(series, days_threshold=THRESHOLD_WEEK) is True

class TestCountOccurrencesInThreshold:
    """Tests for `_count_occurrences_in_threshold`.

    Verifies handling of missing timestamps, empty series and counting
    occurrences for different thresholds.
    """

    def test_missing_timestamp(self, module_factory):
        """Entries without a timestamp should be ignored (count 0)."""
        mod = module_factory()
        series = [{"value": 123}]
        count = mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK)
        assert count == 0

    def test_no_metrics(self, module_factory):
        """Empty series returns zero occurrences."""
        mod = module_factory()
        series = []
        count = mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK)
        assert count == 0

    def test_metrics_within_threshold_7_days(self, module_factory):
        """Count metrics that fall into a 7-day window."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:01:00+00:00",
            "value" : 500
        } ]
        count = mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK)
        assert count == 1
    
    def test_metrics_within_threshold_30_days(self, module_factory):
        """Count metrics that fall into a 30-day window."""
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
        """Mix of recent and old metrics should only count recent ones."""
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
        count = mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK)
        assert count == 1

    def test_invalid_timestamp_format(self, module_factory):
        """Invalid timestamp strings should be ignored and not counted."""
        mod = module_factory()
        series = [{"timestamp": "not-a-timestamp", "value": 100},
                  {"timestamp": "2025-11-04T22:01:00+00:00", "value": 1}]
        count = mod._count_occurrences_in_threshold(series, days_threshold=THRESHOLD_WEEK)
        assert count == 1

class TestSumMetricsLastMonth:
    """Tests for `_sum_metrics_last_month`.

    Ensures only metrics inside the last 30 days are summed and that
    the exact 30-day boundary is included.
    """

    def test_no_metrics(self, module_factory):
        """Empty series returns sum of zero."""
        mod = module_factory()
        series = []
        sum = mod._sum_metrics_last_month(series)
        assert sum == 0

    def test_metrics_within_7_days(self, module_factory):
        """Recent metrics within 7 days contribute to the sum."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:22:01+00:00",
            "value" : 500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 500

    def test_metrics_within_30_days(self, module_factory):
        """Metrics within 30 days are included in the monthly sum."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T00:00:00+00:00",
            "value" : 3000
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 3000

    def test_metrics_exact_30_days(self, module_factory):
        """Metric exactly 30 days old should be included in the sum."""
        mod = module_factory()
        series= [{
            "timestamp" : "2025-10-08T00:00:00+00:00",
            "value" : 1500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 1500

    def test_metrics_outside_threshold(self, module_factory):
        """All metrics older than 30 days are ignored (sum 0)."""
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
        """Only metrics within 30 days contribute to the returned sum."""
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

    def test_negative_values_are_ignored(self, module_factory):
        """Negative values should be ignored in the sum."""
        mod = module_factory()
        series = [
            {"timestamp": "2025-11-04T22:00:00+00:00", "value": 1000},
            {"timestamp": "2025-11-03T00:00:00+00:00", "value": -500},
        ]
        total = mod._sum_metrics_last_month(series)
        assert total == 1000

    def test_invalid_values_are_ignored(self, module_factory):
        """Non-numeric values should not affect the sum."""
        mod = module_factory()
        series = [
            {"timestamp": "2025-11-04T22:01:00+00:00", "value": 1000},
            {"timestamp": "2025-11-03T00:00:00+00:00"},
        ]
        total = mod._sum_metrics_last_month(series)
    
        assert total == 1000

    def test_invalid_timestamp_formats_are_ignored(self, module_factory):
        """Entries with invalid timestamp formats should be ignored when summing recent metrics."""
        mod = module_factory()
        series = [
            {"timestamp": "not-a-timestamp", "value": 500},
            {"timestamp": "2025-11-04T22:01:00+00:00", "value": 1000},
        ]
        total = mod._sum_metrics_last_month(series)
        assert total == 1000

class TestInactivity:
    """Tests for `_is_inactive` which decides if a resource is inactive.
    """

    def test_empty_resource(self, module_factory):
        """Resource without retention or metrics is considered inactive."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is True

    def test_has_lifecycle(self, module_factory):
        """Presence of a retention policy marks the resource as active."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["retention_in_days"] = 3
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_recent_ingestion(self, module_factory):
        """Recent ingestion metric makes the resource active."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-11-04T22:01:00+00:00",
          "value" : 500
        }]
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_ingestion_exact_threshold(self, module_factory):
        """An ingestion metric on the edge of the threshold counts as recent."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [{
         "timestamp" : "2025-10-31T00:00:00+00:00",
          "value" : 2500
        }]
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_ingestion_outside_threshold(self, module_factory):
        """Only old ingestion metrics makes the resource inactive."""
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is True

    def test_ingestion_inside_and_outside_threshold(self, module_factory):
        """If any ingestion metric is recent, resource is active."""
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_recent_query(self, module_factory):
        """Recent query metric makes the resource active."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-11-04T18:30:00+00:00",
        "value" : 1000
        }]
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_query_exact_threshold(self, module_factory):
        """A query metric exactly on the threshold counts as recent."""
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["query"] = [{
        "timestamp" : "2025-10-31T00:00:00+00:00",
        "value" : 2000
        }]
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_query_outside_threshold(self, module_factory):
        """Old query metrics do not prevent resource from being inactive."""
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is True

    def test_query_inside_and_outside_threshold(self, module_factory):
        """Presence of any recent query metric marks resource as active."""
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_recent_query_and_ingestion(self, module_factory):
        """Recent metrics across multiple categories keep resource active."""
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is False

    def test_query_and_ingestion_outside_threshold(self, module_factory):
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
        assert mod._is_inactive(resource, THRESHOLD_WEEK) is True

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
            "metrics": {
                MetricKey.INGESTION.value: [],
                MetricKey.QUERY.value: [],
            }
        }]))
        mod._is_inactive = Mock(return_value=True)
        mod._real_saving_payload = Mock(return_value={"saving": 0.5})
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
        mod.get_options_values = Mock(return_value=(THRESHOLD_WEEK, {excluded_pool}, set()))
        ca_map = {"acc1": {"id": "acc1", "type": "aws", "name": "Account 1"}}
        mod.get_cloud_accounts = Mock(return_value=ca_map)
        mod._extract_cloud_account_id = Mock(return_value="acc1")
        mod._aggregate_resources = Mock(return_value = ([
            {
                "resource_id": "r1",
                "cloud_account_id": "acc1",
                "pool_id": excluded_pool,
                "name": "log-group-1",
                "region": "us-east-1",
                "metrics": {
                    MetricKey.INGESTION.value: [],
                    MetricKey.QUERY.value: []
                }
            }
        ]))
        mod._is_inactive = Mock(return_value=True)
        mod._real_saving_payload = Mock(return_value={"saving": 0})
        mod._count_occurrences_in_threshold = Mock(return_value=0)

        result = mod._get()
        assert result[0]["is_excluded"] is True

    def test_skip_cloud_accounts(self, mod_base):
        """"Skips cloud accounts in `skip_cloud_accounts`."""
        mod = mod_base
        mod.get_options_values = Mock(return_value=(THRESHOLD_WEEK, set(), {"acc1"}))
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
            {
                "resource_id": "r1",
                "cloud_account_id": "acc1",
                "pool_id": "p1",
                "name": "log-group-1",
                "region": "us-east-1",
                "metrics": {
                    MetricKey.INGESTION.value: [{"timestamp": "2025-11-04T00:00:00+00:00"}],
                    MetricKey.QUERY.value: [{"timestamp": "2025-11-03T00:00:00+00:00"}],
                }
            },
        ]))
        mod._is_inactive = Mock(return_value=True)
        mod._real_saving_payload = Mock(return_value={"saving": 0.42})
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
