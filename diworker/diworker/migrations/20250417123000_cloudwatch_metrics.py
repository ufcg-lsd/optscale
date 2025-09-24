import logging

from diworker.diworker.migrations.base import BaseMigration
import clickhouse_connect
from optscale_client.rest_api_client.client_v2 import Client as RestClient

LOG = logging.getLogger(__name__)


class Migration(BaseMigration):

    def get_clickhouse_client(self):
        user, password, host, db_name, port, secure = (
            self.config_cl.clickhouse_params())
        return clickhouse_connect.get_client(
                host=host, password=password, database=db_name, user=user,
                port=port, secure=secure)
    def upgrade(self):
        clickhouse_cl = self.get_clickhouse_client()
        clickhouse_cl.command("""
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
        clickhouse_cl = self.get_clickhouse_client()
        clickhouse_cl.command(
            "DROP TABLE IF EXISTS cloudwatch_metrics"
        )
