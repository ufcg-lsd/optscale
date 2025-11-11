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


#
# Note: No module-level skip to allow running implemented tests (e.g., TC-06).


class TestParseTs:
    """RQ-01 — Timestamp parser (TC-01 to TC-04)."""

    def test_tc_01_epoch_seconds(self, module_factory):
        pytest.skip("Implement TC-01: epoch seconds.")

    def test_tc_02_iso_without_tz(self, module_factory):
        pytest.skip("Implement TC-02: ISO without timezone.")

    def test_tc_03_iso_with_z(self, module_factory):
        pytest.skip("Implement TC-03: ISO with Z suffix.")

    def test_tc_04_invalid(self, module_factory):
        pytest.skip("Implement TC-04: invalid value.")

class TestHasRecentMetrics:
    def test_no_metrics(self, module_factory):
        mod = module_factory()
        series = []
        assert mod._has_recent_metrics(series, days_threshold=7) is False
        assert mod._count_occurrences_in_threshold(series, days_threshold=7) == 0

    def test_metrics_outside_threshold(self, module_factory):
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
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T12:00:00+00:00",
            "value" : 2500
        } ]
        assert mod._has_recent_metrics(series, days_threshold=7) is True

class TestCountOccurrencesInThreshold:

    def test_missing_timestamp(self, module_factory):
        mod = module_factory()
        series = [{"value": 123}]
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 0

    def test_no_metrics(self, module_factory):
        mod = module_factory()
        series = []
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 0

    def test_metrics_within_threshold_7_days(self, module_factory):
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:01:00+00:00",
            "value" : 500
        } ]
        count = mod._count_occurrences_in_threshold(series, days_threshold=7)
        assert count == 1
    
    def test_metrics_within_threshold_30_days(self, module_factory):
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

    def test_no_metrics(self, module_factory):
        mod = module_factory()
        series = []
        sum = mod._sum_metrics_last_month(series)
        assert sum == 0

    def test_metrics_within_7_days(self, module_factory):
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-04T22:22:01+00:00",
            "value" : 500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 500

    def test_metrics_within_30_days(self, module_factory):
        mod = module_factory()
        series= [{
            "timestamp" : "2025-11-01T00:00:00+00:00",
            "value" : 3000
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 3000

    def test_metrics_exact_30_days(self, module_factory):
        mod = module_factory()
        series= [{
            "timestamp" : "2025-10-08T00:00:00+00:00",
            "value" : 1500
        } ]
        sum = mod._sum_metrics_last_month(series)
        assert sum == 1500

    def test_metrics_outside_threshold(self, module_factory):
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
    """RQ-04 — Inactivity determination (TC-10 to TC-15)."""

    def test_tc_10_inactive_true(self, module_factory):
        pytest.skip("Implement TC-10: resource is inactive.")

    def test_tc_11_has_lifecycle(self, module_factory):
        pytest.skip("Implement TC-11: retention is defined.")

    def test_tc_12_has_recent_ingestion(self, module_factory):
        pytest.skip("Implement TC-12: recent ingestion.")

    def test_tc_13_has_recent_query(self, module_factory):
        pytest.skip("Implement TC-13: recent query.")

    def test_tc_14_corrupted_data(self, module_factory):
        pytest.skip("Implement TC-14: malformed resource.")

    def test_tc_15_custom_threshold(self, module_factory):
        pytest.skip("Implement TC-15: custom threshold.")


class TestSaving:
    """RQ-05 — Saving calculation (TC-16 to TC-20)."""

    def test_ingestion_last_month_0(self, module_factory):
        mod = module_factory()
        resource = copy.deepcopy(RESOURCE_LOG_GROUP)
        resource["meta"]["metrics"]["ingestion"] = [ {
            "timestamp" : "2025-10-21T12:15:00+00:00",
            "value" : 2000
        } ]
        saving = mod._estimate_saving(resource)
        assert saving == pytest.approx(9.31e-07, rel=1e-3)
    

    def test_tc_16_storage_only(self, module_factory):
        pytest.skip("Implement TC-16: storage only.")

    def test_tc_17_with_ingestion(self, module_factory):
        pytest.skip("Implement TC-17: ingestion adds cost.")

    def test_tc_18_with_query(self, module_factory):
        pytest.skip("Implement TC-18: query adds cost.")

    def test_tc_19_bytes_to_gib_conversion(self, module_factory):
        pytest.skip("Implement TC-19: bytes→GiB conversion.")

    def test_tc_20_safe_exception(self, module_factory):
        pytest.skip("Implement TC-20: safe 0.0 on exceptions.")


class TestUtilsContract:
    """RQ-06 / RQ-07 — Extraction and reading utilities (TC-21 to TC-25)."""

    def test_tc_21_extract_cloud_account_id_str(self, module_factory):
        pytest.skip("Implement TC-21: _extract_cloud_account_id (str).")

    def test_tc_22_extract_cloud_account_id_dict(self, module_factory):
        pytest.skip("Implement TC-22: _extract_cloud_account_id (dict).")

    def test_tc_23_get_from_resource_prefers_resource(self, module_factory):
        pytest.skip("Implement TC-23: resource[key] has priority.")

    def test_tc_24_get_from_resource_falls_back_to_meta(self, module_factory):
        pytest.skip("Implement TC-24: meta[key] as fallback.")

    def test_tc_25_get_metrics_with_fallback(self, module_factory):
        pytest.skip("Implement TC-25: fallback to meta.metrics.")


class TestIntegration:
    """RQ-08 — Integration of `_get` with `_aggregate_resources`."""

    def test_tc_26_basic_pipeline(self, module_factory):
        pytest.skip("Implement TC-26: basic pipeline and output structure.")

    def test_tc_27_filter_excluded_pools(self, module_factory):
        pytest.skip("Implement TC-27: exclusion by pool.")

    def test_tc_28_skip_cloud_accounts(self, module_factory):
        pytest.skip("Implement TC-28: skipped cloud accounts.")

    def test_tc_29_aggregated_metrics(self, module_factory):
        pytest.skip("Implement TC-29: aggregated metrics in final item.")

    def test_tc_30_aggregate_resources_projection(self, module_factory):
        pytest.skip("Implement TC-30: aggregation pipeline contract.")


# Enum used in many scenarios — imported here to avoid unused symbol lint.
_ = MetricKey


