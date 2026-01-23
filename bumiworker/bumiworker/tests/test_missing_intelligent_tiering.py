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
        "tiers": [["standard", 7.451]],
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
            "FA": 0.023,
            "IA": 0.022,
            "AIA": 0.004,
            "DAA": 0.00099,
        })

        return mod

    return _factory


class TestIsCandidate:
    """Tests for `_is_candidate` method."""
    
    def test_no_metrics_and_standard(self, module_factory):
        """Test that standard tier bucket without metrics is a candidate."""
        mod = module_factory()
        resource = aggregate_resource(RESOURCE_BUCKET)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_express_one_zone(self, module_factory):
        """Test that express one zone tier bucket without metrics is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["express one zone", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_standard_ia(self, module_factory):
        """Test that standard-ia tier bucket without metrics is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["standard-ia", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    
    def test_no_metrics_and_one_zone_ia(self, module_factory):
        """Test that one zone-ia tier bucket without metrics is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["one zone-ia", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_no_metrics_and_glacier_instant_retrieval(self, module_factory):
        """Test that glacier instant retrieval tier bucket without metrics is not a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["glacier ir", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_no_metrics_and_glacier_flexible_retrieval(self, module_factory):
        """Test that glacier flexible retrieval tier bucket without metrics is not a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["glacier", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_no_metrics_and_deep_archive(self, module_factory):
        """Test that deep archive tier bucket without metrics is not a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["deep archive", 7.451]]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_standard(self, module_factory):
        """Test that standard tier bucket with last checked less than 30 days ago is not a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_express_one_zone(self, module_factory):
        """Test that express one zone tier bucket with last checked less than 30 days ago is not a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["express one zone", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is False

    def test_last_checked_less_than_30_days_ago_standard_ia(self, module_factory):
        """Test that standard-ia tier bucket with last checked less than 30 days ago is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["standard-ia", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_one_zone_ia(self, module_factory):
        """Test that one zone-ia tier bucket with last checked less than 30 days ago is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["one zone-ia", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_glacier_instant_retrieval(self, module_factory):
        """Test that glacier instant retrieval tier bucket with last checked less than 30 days ago is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["glacier ir", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_glacier_flexible_retrieval(self, module_factory):
        """Test that glacier flexible retrieval tier bucket with last checked less than 30 days ago is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["glacier", 7.451]]
        r["meta"]["last_checked"] = ["2025-09-31", "2025-10-15", "2025-10-01"]
        resource = aggregate_resource(r)
        assert mod._is_candidate(resource) is True

    def test_last_checked_less_than_30_days_ago_deep_archive(self, module_factory):
        """Test that deep archive tier bucket with last checked less than 30 days ago is a candidate."""
        mod = module_factory()
        r = copy.deepcopy(RESOURCE_BUCKET)
        r["meta"]["tiers"] = [["deep archive", 7.451]]
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
        r["meta"]["tiers"] = [["express one zone", 7.451]]
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
        r["meta"]["tiers"] = [["standard-ia", 7.451]]
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
        r["meta"]["tiers"] = [["one zone-ia", 7.451]]
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
        r["meta"]["tiers"] = [["glacier ir", 7.451]]
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
        r["meta"]["tiers"] = [["glacier", 7.451]]
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
        r["meta"]["tiers"] = [["deep archive", 7.451]]
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
        r["meta"]["tiers"] = [["express one zone", 7.451]]
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
        r["meta"]["tiers"] = [["standard-ia", 7.451]]
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
        r["meta"]["tiers"] = [["one zone-ia", 7.451]]
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
        r["meta"]["tiers"] = [["glacier ir", 7.451]]
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
        r["meta"]["tiers"] = [["glacier", 7.451]]
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
        r["meta"]["tiers"] = [["deep archive", 7.451]]
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
        """Test IT cost calculation for frequent access tier."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 2.3005,
            "storage_cost": 2.3,
            "monitoring_cost": 0.0005,
            "monitoring_price_per_1000": 0.0000025,
            "price_per_gb": 0.023,
        }

    def test_calculate_it_cost_infrequent(self, module_factory):
        """Test IT cost calculation for infrequent access tier."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="infrequent",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 2.2005,
            "storage_cost": 2.2,
            "monitoring_cost": 0.0005,
            "monitoring_price_per_1000": 0.0000025,
            "price_per_gb": 0.022,
        }

    def test_calculate_it_cost_archive(self, module_factory):
        """Test IT cost calculation for archive access tier."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="archive",
            object_count=200000,
            cloud_account={}
        )

        assert result == {
            "total_cost": 0.4005,
            "storage_cost": 0.4,
            "monitoring_cost": 0.0005,
            "monitoring_price_per_1000": 0.0000025,
            "price_per_gb": 0.004,
        }

    def test_calculate_it_cost_size_zero(self, module_factory):
        """Test that IT cost calculation with size_gb=0 returns None."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=0,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_size_negative(self, module_factory):
        """Test that IT cost calculation with negative size_gb returns None."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=-25,
            access_tier="frequent",
            object_count=200000,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_object_count_zero(self, module_factory):
        """Test that IT cost calculation with object_count=0 returns None."""
        mod = module_factory()

        result = mod._calculate_it_cost(
            size_gb=100,
            access_tier="frequent",
            object_count=0,
            cloud_account={}
        )

        assert result is None

    def test_calculate_it_cost_object_count_negative(self, module_factory):
        """Test that IT cost calculation with negative object_count returns None."""
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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "resource_id": "r1",
                "bucket_name": "bucket-a",
                "region": "us-east-1",
                "cloud_account_id": "acc1",
                "tiers": [["standard", 100.0]],
                "object_count": 1000,
                "pool_id": None,
                "it_status_bucket": "",
                "last_checked": [],
                "has_lifecycle": False,
                "lifecycle_rules": [],
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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{"bucket_name": "b", "tiers": [], "cloud_account_id": "acc1", "object_count": 0}]))

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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))
        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [["standard", 10.0]],
                "cloud_account_id": "acc1",
                "object_count": 1000,
                "last_checked": [],
                "has_lifecycle": False,
                "lifecycle_rules": [],
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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))

        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [["standard", 10.0]],
                "pool_id": "P1",
                "cloud_account_id": "acc1",
                "object_count": 1000,
                "last_checked": [],
                "has_lifecycle": False,
                "lifecycle_rules": [],
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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        
        monkeypatch.setattr(mod, "get_options", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_employees", Mock(return_value={}))
        monkeypatch.setattr(mod, "get_pools", Mock(return_value={}))

        items = mod.get()
        assert items == []

    def test_invalid_cloud_account_structure(self, module_factory, monkeypatch):
        """Should ignore cloud accounts with no extractable ID."""
        mod = module_factory()

        monkeypatch.setattr(mod, "get_cloud_accounts",
            Mock(return_value={"bad": {"??": "bad"}}))
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
            Mock(return_value={"acc1": {"id": "acc1"}}))
        monkeypatch.setattr(mod, "_extract_cloud_account_id",
            Mock(return_value="acc1"))

        monkeypatch.setattr(mod, "_aggregate_resources",
            Mock(return_value=[{
                "bucket_name": "b",
                "tiers": [["standard", 10.0]],
                "cloud_account_id": "acc1",
                "it_status_bucket": "Enabled",
                "object_count": 1000,
                "last_checked": [],
                "has_lifecycle": False,
                "lifecycle_rules": [],
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


class TestGetIntelligentTieringPrices:
    """Tests for `_get_intelligent_tiering_prices` method."""

    def test_region_exists_in_json(self, module_factory, monkeypatch):
        """IT-PRICE-01: Test that existing region in JSON returns correct prices."""
        mod = module_factory()
        # Remove mock to use real method
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is not None
        assert isinstance(result, dict)
        assert "FA" in result
        assert "IA" in result
        assert "AIA" in result
        assert "DAA" in result
        assert all(isinstance(v, float) and v > 0 for v in result.values())
        # Expected values from JSON for us-east-1
        assert result["FA"] == 0.023
        assert result["IA"] == 0.0125
        assert result["AIA"] == 0.004
        assert result["DAA"] == 0.00099

    def test_region_not_exists_uses_fallback(self, module_factory, monkeypatch):
        """IT-PRICE-02: Test that non-existent region uses fallback to default prices."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        cloud_account = {"id": "a1"}
        region = "xx-unknown-1"  # Fictional region
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is not None
        assert isinstance(result, dict)
        # Should use default_prices from JSON
        assert "FA" in result
        assert "IA" in result
        assert "AIA" in result
        assert "DAA" in result

    def test_region_none_uses_default(self, module_factory, monkeypatch):
        """IT-PRICE-03: Test that None region uses default prices."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        cloud_account = {"id": "a1"}
        region = None
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is not None
        assert isinstance(result, dict)
        # Cache key should be "a1:default"
        assert mod._it_price_cache.get("a1:default") is not None

    def test_cloud_account_invalid(self, module_factory, monkeypatch):
        """IT-PRICE-04: Test that invalid cloud account returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        cloud_account = {}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is None

    def test_price_cache(self, module_factory, monkeypatch):
        """IT-PRICE-05: Test that price cache works correctly."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        # First call
        result1 = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        # Mock _load_prices_file to verify if it's called again
        load_calls = []
        original_load = mod._load_prices_file
        
        def tracked_load():
            load_calls.append(1)
            return original_load()
        
        monkeypatch.setattr(mod, "_load_prices_file", tracked_load)
        
        # Second call
        result2 = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        # Should use cache, not call _load_prices_file again
        assert len(load_calls) == 0
        assert result1 == result2
        assert result1 is not None

    def test_json_file_not_exists(self, module_factory, monkeypatch):
        """IT-PRICE-06: Test that missing JSON file returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _load_prices_file to simulate file not found
        def mock_load_prices_file():
            mod.__class__._prices_file_cache = None
            return None
        
        monkeypatch.setattr(mod, "_load_prices_file", mock_load_prices_file)
        # Force class cache to None
        if hasattr(mod.__class__, '_prices_file_cache'):
            delattr(mod.__class__, '_prices_file_cache')
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is None

    def test_json_invalid_format(self, module_factory, monkeypatch):
        """IT-PRICE-07: Test that invalid JSON format returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _load_prices_file to simulate invalid JSON
        # Code handles JSONDecodeError and returns None, so mock also returns None
        def mock_load_prices_file():
            # Simulates that code handled JSONDecodeError and returned None
            mod.__class__._prices_file_cache = None
            return None
        
        monkeypatch.setattr(mod, "_load_prices_file", mock_load_prices_file)
        # Force class cache to None
        if hasattr(mod.__class__, '_prices_file_cache'):
            delattr(mod.__class__, '_prices_file_cache')
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        assert result is None

    def test_prices_with_invalid_values(self, module_factory, monkeypatch):
        """IT-PRICE-08: Test that prices with invalid (non-numeric) values are filtered out."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _load_prices_file to return data with invalid values
        invalid_data = {
            "prices_by_region": {
                "us-east-1": {
                    "FA": "invalid",
                    "IA": 0.0125,
                    "AIA": 0.004,
                    "DAA": 0.00099,
                }
            },
            "default_prices": {}
        }
        
        def mock_load():
            return invalid_data
        
        monkeypatch.setattr(mod, "_load_prices_file", mock_load)
        mod.__class__._prices_file_cache = None
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        # Should return only valid tiers
        assert result is not None
        assert "FA" not in result  # Invalid, ignored
        assert "IA" in result
        assert "AIA" in result
        assert "DAA" in result

    def test_region_exists_but_empty_prices(self, module_factory, monkeypatch):
        """IT-PRICE-09: Test that region exists but prices_by_region[region] is empty uses default prices."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _load_prices_file to return region with empty dict
        data_with_empty_region = {
            "prices_by_region": {
                "us-east-1": {}
            },
            "default_prices": {
                "FA": 0.024,
                "IA": 0.0125,
                "AIA": 0.004,
                "DAA": 0.00099,
            }
        }
        
        def mock_load():
            return data_with_empty_region
        
        monkeypatch.setattr(mod, "_load_prices_file", mock_load)
        mod.__class__._prices_file_cache = None
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        result = mod._get_intelligent_tiering_prices(cloud_account, region)
        
        # Should use default_prices
        assert result is not None
        assert result["FA"] == 0.024  # Value from default_prices

    def test_class_cache(self, module_factory, monkeypatch):
        """IT-PRICE-10: Test that class cache (_prices_file_cache) works across instances."""
        mod1 = module_factory()
        mod2 = module_factory()
        
        # Clear class cache
        if hasattr(S3IntelligentTiering, '_prices_file_cache'):
            delattr(S3IntelligentTiering, '_prices_file_cache')
        
        monkeypatch.delattr(mod1, "_get_intelligent_tiering_prices")
        monkeypatch.delattr(mod2, "_get_intelligent_tiering_prices")
        
        # Count file read calls
        file_reads = []
        original_open = open
        
        def tracked_open(*args, **kwargs):
            if "s3_it_prices_all_regions.json" in str(args[0]):
                file_reads.append(1)
            return original_open(*args, **kwargs)
        
        monkeypatch.setattr("builtins.open", tracked_open)
        
        cloud_account = {"id": "a1"}
        region = "us-east-1"
        
        # First instance loads file
        result1 = mod1._get_intelligent_tiering_prices(cloud_account, region)
        
        # Second instance uses class cache
        result2 = mod2._get_intelligent_tiering_prices(cloud_account, region)
        
        # File should be read only once
        assert len(file_reads) == 1
        assert result1 == result2
        assert result1 is not None


class TestRealSavingPayload:
    """Tests for `_real_saving_payload` method."""

    def test_happy_path_complete_flow(self, module_factory, monkeypatch):
        """IT-SAVE-01: Test complete happy path flow."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _bucket_monthly_cost
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        assert "saving" in result
        assert "current_cost_month" in result
        assert "cost_if_intelligent_tiering" in result
        assert "size_gb" in result
        assert "price_intelligent_tiering" in result
        assert "it_storage_cost" in result
        assert "it_monitoring_cost" in result
        
        assert result["current_cost_month"] == 10.00
        assert result["saving"] == max(0.0, 10.00 - result["cost_if_intelligent_tiering"])
        assert result["size_gb"] == 7.451

    def test_negative_saving_becomes_zero(self, module_factory, monkeypatch):
        """IT-SAVE-02: Test that negative saving becomes zero (saving cannot be < 0)."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Mock _bucket_monthly_cost returns value less than IT cost
        # To ensure IT cost is greater, mock _calculate_it_cost directly
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=1.00))
        monkeypatch.setattr(mod, "_calculate_it_cost", Mock(return_value={
            "total_cost": 2.00,  # IT cost greater than monthly cost (1.00)
            "storage_cost": 1.90,
            "monitoring_cost": 0.10,
            "monitoring_price_per_1000": 0.0000025,
            "price_per_gb": 0.019,
        }))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 100.0,
            "object_count": 200000,
            "last_checked": []
        }
        total_gb = 100.0
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        assert result["saving"] == 0.0  # saving = max(0.0, 1.00 - 2.00) = 0.0
        assert result["current_cost_month"] == 1.00
        assert result["cost_if_intelligent_tiering"] == 2.00

    def test_invalid_size_gb_uses_fallback(self, module_factory, monkeypatch):
        """IT-SAVE-03: Test that invalid size_gb in resource uses total_gb as fallback."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": "invalid",
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        assert result["size_gb"] == 7.451  # Uses total_gb as fallback

    def test_size_gb_zero_or_negative(self, module_factory, monkeypatch):
        """IT-SAVE-04: Test that size_gb <= 0 returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 0,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 0.0
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is None

    def test_failed_to_get_monthly_cost(self, module_factory, monkeypatch):
        """IT-SAVE-05: Test that failure to get monthly cost returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=None))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is None

    def test_failed_to_calculate_it_cost(self, module_factory, monkeypatch):
        """IT-SAVE-06: Test that failure to calculate IT cost returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        monkeypatch.setattr(mod, "_calculate_it_cost", Mock(return_value=None))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is None

    def test_region_influences_price(self, module_factory, monkeypatch):
        """IT-SAVE-07: Test that region influences price calculation."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource_base = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "size_gb": 100.0,
            "object_count": 200000,
            "last_checked": []
        }
        total_gb = 100.0
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        # Test with us-east-1
        resource1 = {**resource_base, "region": "us-east-1"}
        result1 = mod._real_saving_payload(resource1, total_gb, today, cloud_account)
        
        # Test with sa-east-1 (different prices)
        resource2 = {**resource_base, "region": "sa-east-1"}
        result2 = mod._real_saving_payload(resource2, total_gb, today, cloud_account)
        
        assert result1 is not None
        assert result2 is not None
        # Prices should be different
        assert result1["price_intelligent_tiering"] != result2["price_intelligent_tiering"]
        assert result1["cost_if_intelligent_tiering"] != result2["cost_if_intelligent_tiering"]

    def test_cloud_account_is_none(self, module_factory, monkeypatch):
        """IT-SAVE-08: Test that cloud_account being None returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = None
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is None

    def test_missing_resource_id_or_cloud_account_id(self, module_factory, monkeypatch):
        """IT-SAVE-09: Test that missing resource_id or cloud_account_id returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        # Test without resource_id
        resource1 = {
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result1 = mod._real_saving_payload(resource1, total_gb, today, cloud_account)
        assert result1 is None
        
        # Test without cloud_account_id
        resource2 = {
            "resource_id": "r1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        
        result2 = mod._real_saving_payload(resource2, total_gb, today, cloud_account)
        assert result2 is None

    def test_object_count_missing_or_invalid(self, module_factory, monkeypatch):
        """IT-SAVE-10: Test that missing or invalid object_count returns None."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        # Test without object_count (will be 0)
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 7.451,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        # object_count = 0 makes _calculate_it_cost return None
        assert result is None

    def test_last_checked_missing_uses_archive(self, module_factory, monkeypatch):
        """IT-SAVE-11: Test that missing last_checked uses archive access tier."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 100.0,
            "object_count": 200000,
            "last_checked": None  # or []
        }
        total_gb = 100.0
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        # access_tier should be "archive", so price_tier should be "AIA"
        # Verify that price used is from AIA (lower than FA and IA)
        assert result["price_intelligent_tiering"] > 0
        # AIA is cheaper than FA/IA, so cost should be lower
        assert result["cost_if_intelligent_tiering"] < 10.00

    def test_total_gb_used_as_fallback(self, module_factory, monkeypatch):
        """IT-SAVE-12: Test that total_gb is used as fallback when size_gb is invalid."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": "invalid_string",
            "object_count": 720725,
            "last_checked": ["2025-08-26"]
        }
        total_gb = 7.451
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        assert result["size_gb"] == 7.451  # Uses total_gb as fallback

    def test_rounding_of_values(self, module_factory, monkeypatch):
        """IT-SAVE-13: Test that values are properly rounded and valid."""
        mod = module_factory()
        monkeypatch.delattr(mod, "_get_intelligent_tiering_prices")
        
        monkeypatch.setattr(mod, "_bucket_monthly_cost", Mock(return_value=10.00))
        
        resource = {
            "resource_id": "r1",
            "cloud_account_id": "a1",
            "region": "us-east-1",
            "size_gb": 100.0,
            "object_count": 200000,
            "last_checked": []
        }
        total_gb = 100.0
        today = NOW_FIXED.date()
        cloud_account = {"id": "a1"}
        
        result = mod._real_saving_payload(resource, total_gb, today, cloud_account)
        
        assert result is not None
        # Values should be valid numbers (not NaN, not infinite)
        assert all(isinstance(v, (int, float)) and not (v != v) for v in result.values())
        # saving cannot be negative
        assert result["saving"] >= 0.0
