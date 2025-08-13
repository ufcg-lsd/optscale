import logging
from diworker.diworker.migrations.base import BaseMigration

LOG = logging.getLogger(__name__)

class Migration(BaseMigration):
    @property
    def mongo_bucket_info(self):
        return self.db.aws_bucket_intelligent_tiering_info

    def upgrade(self):
        self.mongo_bucket_info.create_index(
            [("cloud_account_id", 1), ("bucket_name", 1)], unique=True)
        self.mongo_bucket_info.create_index("bucket_name")
        LOG.info("Created aws_bucket_intelligent_tiering_info collection with indexes.")

    def downgrade(self):
        self.db.drop_collection("aws_bucket_intelligent_tiering_info")
        LOG.info("Dropped aws_bucket_intelligent_tiering_info collection.")
