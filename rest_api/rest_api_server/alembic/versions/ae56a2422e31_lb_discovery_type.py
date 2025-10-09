""""lb_discovery_type"

Revision ID: ae56a2422e31
Revises: 6d1417595f7f
Create Date: 2025-03-12 13:17:45.336026

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ae56a2422e31'
down_revision = '6d1417595f7f'
branch_labels = None
depends_on = None


old_res_types = sa.Enum('instance', 'volume', 'snapshot', 'bucket', 'k8s_pod',
                        'snapshot_chain', 'rds_instance', 'ip_address',
                        'image')
new_res_types = sa.Enum('instance', 'volume', 'snapshot', 'bucket', 'k8s_pod',
                        'snapshot_chain', 'rds_instance', 'ip_address',
                        'image', 'load_balancer', 'log_group')


def upgrade():
    op.alter_column('discovery_info', 'resource_type',
                    existing_type=old_res_types,
                    type_=new_res_types, nullable=False)


def downgrade():
    di_t = sa.sql.table('discovery_info', sa.sql.column(
        'resource_type', new_res_types))
    op.execute(di_t.delete().where(di_t.c.resource_type == 'load_balancer'))
    op.alter_column('discovery_info', 'resource_type',
                    existing_type=new_res_types,
                    type_=old_res_types, nullable=False)
