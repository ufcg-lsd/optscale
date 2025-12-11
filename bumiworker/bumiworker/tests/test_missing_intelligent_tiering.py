from datetime import datetime, timezone
from typing import Callable, Dict
from unittest.mock import Mock
import copy

import pytest  # type: ignore

from bumiworker.modules.recommendations.s3_intelligent_tiering import S3IntelligentTiering, _classify_access_tier_from_last_checked

NOW_FIXED = datetime(2025, 11, 7, 0, 0, 0, tzinfo=timezone.utc)

RESOURCE_BUCKET = {
    "_id": "id1",
    "cloud_account_id": "a1",
    "cloud_resource_id": "r1",
    "_first_seen_date": "2025-08-01T00:00:00Z",
    "_last_seen_date": "2025-11-07T00:00:00Z",
    "applied_rules": [],
    "created_at": 1763411477,
    "deleted_at": 0,
    "employee_id": "e1",
    "first_seen": 1759276800,
    "last_seen": 1763995577,
    "meta": {
        "cloud_console_link": "",
        "is_public_policy": False,
        "is_public_acls": False,
        "intelligent_tiering_enabled": False,
        "intelligent_tiering_configs": [],
        "lifecycle_rules": [],
        "storage_class_analysis": [],
        "metrics_configurations": [],
        "total_size_bytes": 8000481875,
        "object_count": 720725,
        "it_status_bucket": "disabled",
        "tiers": [["Standard", 7.451]],
        "last_checked": [],
        "has_lifecycle": False,
    },
    "name": "n1",
    "pool_id": "p1",
    "region": "us-east-1",
    "resource_type": "Bucket",
    "tags": {},
    "service_name": "AmazonS3",
    "last_expense": {"date": 1761868800, "cost": 8.6199041128},
    "total_cost": 395.31249207400003,
    "active": True,
}

def aggregate_resource(r):
    r = copy.deepcopy(r)
    meta = r.pop("meta", {})

    r["resource_id"] = r.pop("_id")
    r["bucket_name"] = r.get("name") or r.get("cloud_resource_id")
    r["it_status_bucket"] = meta.get("it_status_bucket")
    r["tiers"] = meta.get("tiers")
    r["object_count"] = meta.get("object_count")
    r["last_checked"] = meta.get("last_checked")
    r["has_lifecycle"] = meta.get("has_lifecycle")
    r["lifecycle_rules"] = meta.get("lifecycle_rules")

    return r


@pytest.fixture
def module_factory(monkeypatch) -> Callable[..., S3IntelligentTiering]:
    def _factory(
        *,
        organization_id: str = "org-1",
        created_at: int = int(NOW_FIXED.timestamp()),
        cloud_accounts: Dict = None,
    ) -> S3IntelligentTiering:

        mod = S3IntelligentTiering(
            organization_id=organization_id,
            config_client=Mock(),
            created_at=created_at,
        )

        mod._get_intelligent_tiering_prices = Mock(return_value={
            "frequent": 0.023,
            "infrequent": 0.022,
            "archive": 0.004,
        })

        return mod

    return _factory


class TestIsCandidate:
    """Tests for `_is_candidate` method."""
    
    def test_no_metrics_and_standard(self, module_factory):
        mod = module_factory()
        resource = aggregate_resource(RESOURCE_BUCKET)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_express_one_zone(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Express One Zone", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_standard_ia(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Standard-IA", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_one_zone_ia(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["One-Zone-IA", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_no_metrics_and_glacier_instant_retrieval(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier IR", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_no_metrics_and_glacier_flexible_retrieval(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_no_metrics_and_deep_archive(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Deep Archive", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_standard(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_express_one_zone(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Express One Zone", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_standard_ia(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Standard-IA", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_one_zone_ia(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["One Zone-IA", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_glacier_instant_retrieval(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier IR", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_glacier_flexible_retrieval(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_deep_archive(self, module_factory):
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Deep Archive", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_60_days_ago_standard(self, module_factory):
        """Last checked less than 60 days ago an Standard tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_60_days_ago_express_one_zone(self, module_factory):
        """Last checked less than 60 days ago an Express One Zone tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Express-One-Zone", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_60_days_ago_standard_ia(self, module_factory):
        """Last checked less than 60 days ago an Standard-IA tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Standard-IA", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False
 
    def test_last_checked_less_than_60_days_ago_one_zone_ia(self, module_factory):
        """Last checked less than 60 days ago an One Zone-IA tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["One Zone-IA", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_60_days_ago_glacier_instant_retrieval(self, module_factory):
        """Last checked less than 60 days ago an Glacier Instant Retrieval tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier IR", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_60_days_ago_glacier_flexible_retrieval(self, module_factory):
        """Last checked less than 60 days ago an Glacier Flexible Retrieval tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_60_days_ago_deep_archive(self, module_factory):
        """Last checked less than 60 days ago an Deep Archive tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Deep Archive", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-08-15",
            "2025-10-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True


    def test_last_checked_more_than_60_days_ago_standard(self, module_factory):
        """Last checked more than 60 days ago an Standard tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_more_than_60_days_ago_express_one_zone(self, module_factory):
        """Last checked more than 60 days ago an Express One Zone tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Express-One-Zone", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_more_than_60_days_ago_standard_ia(self, module_factory):
        """Last checked more than 60 days ago an Standard-IA tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Standard-IA", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_more_than_60_days_ago_one_zone_ia(self, module_factory):
        """Last checked more than 60 days ago an One Zone-IA tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["One-Zone-IA", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True
    
    def test_last_checked_more_than_60_days_ago_glacier_instant_retrieval(self, module_factory):
        """Last checked more than 60 days ago an Glacier Instant Retrieval tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier IR", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False
    
    def test_last_checked_more_than_60_days_ago_glacier_flexible_retrieval(self, module_factory):
        """Last checked more than 60 days ago an Glacier Flexible Retrieval tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Glacier", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False
    
    def test_last_checked_more_than_60_days_ago_deep_archive(self, module_factory):
        """Last checked more than 60 days ago an Deep Archive tier."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["Deep Archive", 7.451]]
        r["meta"]["last_checked"] = [
            "2025-05-01",
            "2025-06-15",
            "2025-07-01"
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_intelligent_tiering_enabled(self, module_factory):
        """Intelligent tiering enabled."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = ["2025-11-01"]
        r["meta"]["intelligent_tiering_enabled"] = True
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_has_lifecycle_rules(self, module_factory):
        """Has lifecycle rules."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = ["2025-11-01"]
        r["meta"]["lifecycle_rules"] = [
            {
                "Expiration": {
                    "Days": 1
                },
                "ID": "Remove objects after 1 day",
                "Filter": {
                    "Prefix": ""
                },
                "Status": "Enabled"
            }
        ]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

class TestClassifyCategoryFromTier:
	"""Tests for `_classify_category_from_tier` method."""

	def test_standard_tier(self, module_factory):
		"""Standard tier."""
		mod = module_factory()

		category = mod._classify_category_from_tier("standard")
		assert category == "frequent"

	def test_express_one_zone_tier(self, module_factory):
		"""Express One Zone tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("express one zone")

		assert category == "frequent"

	def test_standard_ia_tier(self, module_factory):
		"""Standard-IA tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("standard-ia")

		assert category == "infrequent"

	def test_one_zone_ia_tier(self, module_factory):
		"""One Zone-IA tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("one zone-infrequent access")

		assert category == "infrequent"

	def test_glacier_instant_retrieval_tier(self, module_factory):
		"""Glacier Instant Retrieval tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("glacier instant retrieval")

		assert category == "archive"

	def test_glacier_flexible_retrieval_tier(self, module_factory):
		"""Glacier Flexible Retrieval tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("glacier flexible retrieval")

		assert category == "archive"
	
	def test_deep_archive_tier(self, module_factory):
		"""Deep Archive tier."""
		mod = module_factory()
		category = mod._classify_category_from_tier("glacier deep archive")

		assert category == "archive"
          
class TestWrongAccessTier:
	"""Tests for `_classify_wrong_access_tier` method."""

	def test_less_than_30_days_ago_frequent(self, module_factory):
		"""Last checked less than 30 days ago and frequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("frequent",  ["2025-09-31", "2025-10-15", "2025-10-01"]) is False

	def test_less_than_30_days_ago_infrequent(self, module_factory):
		"""Last checked less than 30 days ago and infrequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("infrequent",  ["2025-09-31", "2025-10-15", "2025-10-01"]) is True
	
	def test_less_than_30_days_ago_archive(self, module_factory):
		"""Last checked less than 30 days ago and archive."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("archive",  ["2025-09-31", "2025-10-15", "2025-10-01"]) is True

	def test_more_than_30_less_than_60_days_ago_frequent(self, module_factory):
		"""Last checked more than 30 but less than 60 days ago and frequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("frequent",  ["2025-05-01", "2025-08-15", "2025-10-01"]) is True

	def test_more_than_30_less_than_60_days_ago_infrequent(self, module_factory):
		"""Last checked more than 30 but less than 60 days ago and infrequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("infrequent",  ["2025-05-01", "2025-08-15", "2025-10-01"]) is False
	
	def test_more_than_30_less_than_60_days_ago_archive(self, module_factory):
		"""Last checked more than 30 but less than 60 days ago and archive."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("archive",  ["2025-05-01", "2025-08-15", "2025-10-01"]) is True

	def test_more_than_60_days_ago_frequent(self, module_factory):
		"""Last checked more than 60 days ago and frequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("frequent",  ["2025-05-01", "2025-06-15", "2025-07-01"]) is True

	def test_more_than_60_days_ago_infrequent(self, module_factory):
		"""Last checked more than 60 days ago and infrequent."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("infrequent",  ["2025-05-01", "2025-06-15", "2025-07-01"]) is True

	def test_more_than_60_days_ago_archive(self, module_factory):
		"""Last checked more than 60 days ago and archive."""
		mod = module_factory()

		assert mod._classify_wrong_access_tier("archive",  ["2025-05-01", "2025-06-15", "2025-07-01"]) is False
          
class Test_ClassifyAccessTierFromLastChecked:
    """Tests for `_classify_access_tier_from_last_checked` method."""

    def test_frequent(self, module_factory):
        """Frequent access tier."""
        category = _classify_access_tier_from_last_checked(["2025-09-31", "2025-10-15", "2025-10-01"], NOW_FIXED.date())
        assert category == "frequent"

    def test_infrequent(self, module_factory):
        """Infrequent access tier."""
        category = _classify_access_tier_from_last_checked(["2025-05-01", "2025-08-15", "2025-10-01"], NOW_FIXED.date())

        assert category == "infrequent"

    def test_archive(self, module_factory):
        """Archive access tier."""
        category = _classify_access_tier_from_last_checked(["2025-05-01", "2025-06-15", "2025-07-01"], NOW_FIXED.date())

        assert category == "archive"

class TestCalculateITCost:
    """Tests for `_calculate_it_cost` method."""

    def test_calculate_it_cost_frequent(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 2.8,
            "storage_cost": 2.3,
            "monitoring_cost": 0.5,
            "monitoring_price_per_1000": 0.0025,
        }

    def test_calculate_it_cost_infrequent(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="infrequent",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 2.7,
            "storage_cost": 2.2,
            "monitoring_cost": 0.5,
            "monitoring_price_per_1000": 0.0025,
        }

    def test_calculate_it_cost_archive(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="archive",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 0.9,
            "storage_cost": 0.4,
            "monitoring_cost": 0.5,
            "monitoring_price_per_1000": 0.0025,
        }

    def test_calculate_it_cost_size_zero(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=0,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_size_negative(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=-25,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_object_count_zero(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="frequent",
            object_count=0,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_object_count_negative(self, module_factory):
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="frequent",
            object_count=-50000,
            cloud_account={}
        )

        assert result is None

class TestGetMethod:
    def test_basic_flow_returns_items(self, module_factory, monkeypatch):
        """Should return a list with one item when candidate and saving > 0."""
        mod = module_factory()
        
        monkeypatch.setattr(mod, "_cloud_account_names",
            Mock(return_value={"acc1": "Account One"}))
        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "resource_id": "r1",
                "bucket_name": "bucket-a",
                "region": "us-east-1",
                "cloud_account_id": "acc1",
                "tiers": [{"tier": "frequent", "gb": 100}],
                "pool_id": None,
                "it_status_bucket": "",
            }]))
        monkeypatch.setattr(mod, "_is_candidate", Mock(return_value=True))
        monkeypatch.setattr(mod, "_real_saving_payload", Mock(return_value={
            "saving": 5.1234,
            "current_cost_month": 10.0,
            "cost_if_intelligent_tiering": 4.8766,
            "size_gb": 100.0,
            "price_intelligent_tiering": 0.023,
        }))

        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))


        items = mod.get()

        assert len(items) == 1
        item = items[0]

        assert item["resource_id"] == "r1"
        assert item["resource_name"] == "bucket-a"
        assert item["saving"] == 5.12
        assert item["current_cost_month"] == 10.0
        assert item["cost_if_intelligent_tiering"] == 4.88
        assert item["size_gb"] == 100.0
        assert item["price_intelligent_tiering"] == 0.023000
        assert item["cloud_account_name"] == "Account One"

    def test_skips_non_candidate(self, module_factory, monkeypatch):
        """Should skip resource when _is_candidate returns False."""
        mod = module_factory()

        monkeypatch.setattr(mod, "_cloud_account_names",
            Mock(return_value={"acc1": "Name"}))
        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{"bucket_name": "b", "tiers": [], "cloud_account_id": "acc1"}]))

        monkeypatch.setattr(mod, "_is_candidate", Mock(return_value=False))

        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))


        items = mod.get()
        assert items == []

    def test_skips_when_saving_zero_or_negative(self, module_factory, monkeypatch):
        """Should not include buckets where saving <= 0."""
        mod = module_factory()

        monkeypatch.setattr(mod, "_cloud_account_names",
            Mock(return_value={"acc1": "Name"}))
        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [{"tier": "frequent", "gb": 10}],
                "cloud_account_id": "acc1",
            }]))

        monkeypatch.setattr(mod, "_is_candidate", Mock(return_value=True))

        monkeypatch.setattr(mod, "_real_saving_payload",
            Mock(return_value={"saving": 0.0}))
        
        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert items == []

    def test_skips_excluded_pools(self, module_factory, monkeypatch):
        """Should not include resources whose pools are in excluded_pools."""
        mod = module_factory()
        mod.get_options = Mock(return_value =({
            "excluded_pools": {"P1": True}
        }))

        monkeypatch.setattr(mod, "_cloud_account_names",
            Mock(return_value={"acc1": "Name"}))
        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))

        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [{"tier": "frequent", "gb": 10}],
                "pool_id": "P1",
                "cloud_account_id": "acc1",
            }]))

        monkeypatch.setattr(mod, "_is_candidate", Mock(return_value=True))

        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert items == []

    def test_skip_cloud_accounts(self, module_factory, monkeypatch):
        """Should fully skip cloud accounts listed in skip_cloud_accounts."""
        mod = module_factory()
        mod.get_options = Mock(return_value = ({
            "skip_cloud_accounts": ["acc1"]
        }))

        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        
        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert items == []

    def test_invalid_cloud_account_structure(self, module_factory, monkeypatch):
        """Should ignore cloud accounts with no extractable ID."""
        mod = module_factory()

        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"??": "bad"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value=None))
        
        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert items == []

    def test_status_with_it(self, module_factory, monkeypatch):
        """Should mark resource as already using IT when status is positive."""
        mod = module_factory()

        monkeypatch.setattr(mod, "_cloud_account_names",
            Mock(return_value={"acc1": "Name"}))
        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value=[{"id": "acc1"}]))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))

        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [{"tier": "frequent", "gb": 10}],
                "cloud_account_id": "acc1",
                "it_status_bucket": "Enabled"
            }]))

        monkeypatch.setattr(mod, "_is_candidate", Mock(return_value=True))
        monkeypatch.setattr(mod, "_real_saving_payload",
            Mock(return_value={"saving": 1.5}))
        
        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert len(items) == 1
        assert items[0]["is_with_intelligent_tiering"] is True
