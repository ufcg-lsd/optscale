import logging
from insider.insider_worker.migrations.base import BaseMigration

INDEXES = {
    'CloudTypeFlavor': ['cloud_type', 'flavor'],
}
LOG = logging.getLogger(__name__)


class Migration(BaseMigration):
    @property
    def architectures(self):
        return self.db.architectures

    def get_indexes(self):
        return [x['name'] for x in self.architectures.list_indexes()]

    def upgrade(self):
        existing_indexes = self.get_indexes()
        for index_name, index_fields in INDEXES.items():
            if index_name in existing_indexes:
                LOG.info(f'Index {index_name} already exists')
                continue
            LOG.info(f'Creating index {index_name}')
            self.architectures.create_index(
                [(f, 1) for f in index_fields],
                name=index_name,
                background=True
            )

    def downgrade(self):
        existing_indexes = self.get_indexes()
        for index_name, index_fields in INDEXES.items():
            if index_name in existing_indexes:
                LOG.info(f'Dropping index {index_name}')
                self.architectures.drop_index(index_name)
            else:
                LOG.info(f'Index {index_name} doesn\'t exist')
