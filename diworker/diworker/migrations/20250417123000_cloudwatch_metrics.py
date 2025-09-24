import logging
from diworker.diworker.migrations.base import BaseMigration

LOG = logging.getLogger(__name__)


class Migration(BaseMigration):
    def upgrade(self):
        self.clickhouse_cl.command("""
            CREATE TABLE IF NOT EXISTS cloudwatch_metrics (
                cloud_account_id String,
                resource_id String,
                metric_name String,
                timestamp DateTime,
                value Float64
            ) ENGINE = MergeTree()
            ORDER BY (cloud_account_id, resource_id, metric_name, timestamp)
        """)

    def downgrade(self):
        self.clickhouse_cl.command(
            "DROP TABLE IF EXISTS cloudwatch_metrics"
        )
