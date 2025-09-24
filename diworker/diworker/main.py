#!/usr/bin/env python
import os
import time

import urllib3
from threading import Thread
from etcd import Lock as EtcdLock
from kombu import Exchange, Queue, Connection as QConnection
from kombu.pools import producers
from kombu.log import get_logger
from kombu.mixins import ConsumerMixin
from kombu.utils.debug import setup_logging
from pymongo import MongoClient
from urllib3.exceptions import InsecureRequestWarning
import clickhouse_connect

from optscale_client.config_client.client import Client as ConfigClient
from optscale_client.rest_api_client.client_v2 import Client as RestClient
from tools.optscale_time.optscale_time import startday, utcfromtimestamp

from diworker.diworker.importers.base import BaseReportImporter
from diworker.diworker.importers.factory import get_importer_class
from diworker.diworker.migrator import Migrator

ACTIVITIES_EXCHANGE_NAME = 'activities-tasks'
ALERT_THRESHOLD = 60 * 60 * 24
EXCHANGE_NAME = 'billing-reports'
QUEUE_NAME = 'report-imports'
task_exchange = Exchange(EXCHANGE_NAME, type='direct')

ARGUMENTS = {'x-max-priority': 10}
task_queue = Queue(
    QUEUE_NAME, task_exchange,
    routing_key=QUEUE_NAME,
    queue_arguments=ARGUMENTS
)

LOG = get_logger(__name__)
ENVIRONMENT_CLOUD_TYPE = 'environment'
HEARTBEAT_INTERVAL = 300


class DIWorker(ConsumerMixin):
    def __init__(self, connection, config_cl):
        self.connection = connection
        self.config_cl = config_cl
        self._rest_cl = None
        self._mongo_cl = None
        self._clickhouse_cl = None
        self.report_import_id = None
        self.thread = Thread(target=self.heartbeat)
        self.thread.start()

    def heartbeat(self):
        while True:
            if self.report_import_id:
                self.rest_cl.report_import_update(self.report_import_id, {})
            time.sleep(HEARTBEAT_INTERVAL)

    @property
    def rest_cl(self):
        if self._rest_cl is None:
            self._rest_cl = RestClient(
                url=self.config_cl.restapi_url(), verify=False)
            self._rest_cl.secret = self.config_cl.cluster_secret()
        return self._rest_cl

    @property
    def mongo_cl(self):
        if self._mongo_cl is None:
            mongo_params = self.config_cl.mongo_params()
            self._mongo_cl = MongoClient(mongo_params[0])
        return self._mongo_cl

    @property
    def clickhouse_cl(self):
        if not self._clickhouse_cl:
            user, password, host, db_name, port, secure = (
                self.config_cl.clickhouse_params())
            self._clickhouse_cl = clickhouse_connect.get_client(
                host=host, password=password, database=db_name, user=user,
                port=port, secure=secure)
        return self._clickhouse_cl

    def publish_activities_task(self, organization_id, object_id, object_type,
                                action, routing_key, meta=None):
        task = {
            'organization_id': organization_id,
            'object_id': object_id,
            'object_type': object_type,
            'action': action,
            'meta': meta
        }
        queue_conn = QConnection('amqp://{user}:{pass}@{host}:{port}'.format(
            **self.config_cl.read_branch('/rabbit')))
        task_exchange = Exchange(ACTIVITIES_EXCHANGE_NAME, type='topic')
        with producers[queue_conn].acquire(block=True) as producer:
            producer.publish(
                task,
                serializer='json',
                exchange=task_exchange,
                declare=[task_exchange],
                routing_key=routing_key,
                retry=True
            )

    def get_consumers(self, Consumer, channel):
        return [Consumer(
            queues=[task_queue],
            accept=['json'],
            callbacks=[self.process_task],
            prefetch_count=1,
        )]

    def report_import(self, task):
        self.report_import_id = task.get('report_import_id')
        if not self.report_import_id:
            raise Exception('invalid task received: {}'.format(task))

        _, import_dict = self.rest_cl.report_import_get(self.report_import_id)
        cloud_acc_id = import_dict.get('cloud_account_id')
        _, resp = self.rest_cl.report_import_list(cloud_acc_id, show_active=True)
        imports = list(filter(
            lambda x: x['id'] != self.report_import_id, resp['report_imports']))
        if imports:
            reason = 'Import cancelled due another import: %s' % imports[0]['id']
            self.rest_cl.report_import_update(
                self.report_import_id, {'state': 'failed',
                                        'state_reason': reason})
            return
        is_recalculation = import_dict.get('is_recalculation', False)
        LOG.info('Starting processing for task: %s, purpose %s',
                 task, 'recalculation ' if is_recalculation else 'import')
        self.rest_cl.report_import_update(self.report_import_id,
                                          {'state': 'in_progress'})

        importer_params = {
            'cloud_account_id': cloud_acc_id,
            'rest_cl': self.rest_cl,
            'config_cl': self.config_cl,
            'mongo_raw': self.mongo_cl.restapi['raw_expenses'],
            'mongo_resources': self.mongo_cl.restapi['resources'],
            'clickhouse_cl': self.clickhouse_cl,
            'import_file': import_dict.get('import_file'),
            'recalculate': is_recalculation}
        importer = None
        ca = None
        previous_attempt_ts = 0
        try:
            _, ca = self.rest_cl.cloud_account_get(
                importer_params.get('cloud_account_id'))
            organization_id = ca.get('organization_id')
            _, org = self.rest_cl.organization_get(organization_id)
            if org.get('disabled'):
                reason = ('Import cancelled due to disabled '
                          'organization: %s') % self.report_import_id
                self.rest_cl.report_import_update(
                    self.report_import_id, {'state': 'failed',
                                            'state_reason': reason})
                return
            start_last_import_ts = ca.get('last_import_at', 0)
            previous_attempt_ts = ca.get('last_import_attempt_at', 0)
            cc_type = ca.get('type')
            export_scheme = ca['config'].get('expense_import_scheme')
            importer = get_importer_class(cc_type, export_scheme)(
                **importer_params)
            importer.import_report()
            self.rest_cl.report_import_update(
                self.report_import_id, {'state': 'completed'})
            if start_last_import_ts == 0 and cc_type != ENVIRONMENT_CLOUD_TYPE:
                all_reports_finished = True
                _, resp = self.rest_cl.cloud_account_list(organization_id)
                for acc in resp['cloud_accounts']:
                    if (acc['type'] != ENVIRONMENT_CLOUD_TYPE and
                            acc['last_import_at'] == 0):
                        all_reports_finished = False
                        break
                if all_reports_finished:
                    self.publish_activities_task(
                        organization_id, organization_id, 'organization',
                        'report_import_passed',
                        'organization.report_import.passed')
        except Exception as exc:
            if hasattr(exc, 'details'):
                # pylint: disable=E1101
                LOG.error('Monga exception details: %s', exc.details)
            reason = str(exc)
            self.rest_cl.report_import_update(
                self.report_import_id,
                {'state': 'failed', 'state_reason': reason}
            )
            now = int(time.time())
            if not importer:
                importer = BaseReportImporter(**importer_params)
            importer.update_cloud_import_attempt(now, reason)
            self.send_report_failed_email(ca, previous_attempt_ts, now)
            raise

    def send_report_failed_email(self, cloud_account, previous_attempt_ts,
                                 now):
        last_import_at = cloud_account['last_import_at']
        if not last_import_at:
            last_import_at = cloud_account['created_at']
        if now - last_import_at < ALERT_THRESHOLD:
            return
        if last_import_at < previous_attempt_ts:
            # previous import failed too
            if startday(utcfromtimestamp(previous_attempt_ts)) == startday(
                    utcfromtimestamp(now)):
                # email already sent today during previous report import fails
                return
        self.publish_activities_task(
            cloud_account['organization_id'], cloud_account['id'],
            'cloud_account', 'report_import_failed',
            'organization.report_import.failed')

    def process_task(self, body, message):
        try:
            self.report_import(body)
        except Exception as exc:
            LOG.exception('Data import failed: %s', str(exc))
        self.report_import_id = None
        message.ack()


if __name__ == '__main__':
    urllib3.disable_warnings(InsecureRequestWarning)
    setup_logging(loglevel='INFO', loggers=[''])

    config_cl = ConfigClient(
        host=os.environ.get('HX_ETCD_HOST'),
        port=int(os.environ.get('HX_ETCD_PORT')),
    )
    config_cl.wait_configured()
    migrator = Migrator(config_cl, 'restapi', 'diworker/diworker/migrations')
    # Use lock to avoid migration problems with several diworkers
    # starting at the same time on cluster
    with EtcdLock(config_cl, 'diworker_migrations'):
        migrator.migrate()
    LOG.info("starting worker")
    conn_str = 'amqp://{user}:{pass}@{host}:{port}'.format(
        **config_cl.read_branch('/rabbit'))
    with QConnection(conn_str) as conn:
        try:
            worker = DIWorker(conn, config_cl)
            worker.run()
        except KeyboardInterrupt:
            print('bye bye')
