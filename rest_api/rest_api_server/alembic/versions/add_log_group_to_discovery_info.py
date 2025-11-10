"""add_log_group_to_discovery_info

Revision ID: add_log_group_to_discovery_info
Revises: c9f036cdbcce
Create Date: 2025-08-10 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_log_group_to_discovery_info'
down_revision = 'c9f036cdbcce'
branch_labels = None
depends_on = None

old_res_types = sa.Enum('instance', 'volume', 'snapshot', 'bucket', 'k8s_pod',
                        'snapshot_chain', 'rds_instance', 'ip_address',
                        'image', 'load_balancer')

new_res_types = sa.Enum('instance', 'volume', 'snapshot', 'bucket', 'k8s_pod',
                        'snapshot_chain', 'rds_instance', 'ip_address',
                        'image', 'load_balancer', 'log_group')


def upgrade():
    """Adds 'log_group' to the resource_type column enum"""
    op.alter_column('discovery_info', 'resource_type',
                    existing_type=old_res_types,
                    type_=new_res_types, nullable=False)


def downgrade():
    """Removes 'log_group' from the resource_type column enum."""
    op.alter_column('discovery_info', 'resource_type',
                    existing_type=new_res_types,
                    type_=old_res_types, nullable=False)
