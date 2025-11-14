from datetime import datetime, timezone
from threading import Thread

import os
import time
import logging
import urllib3

from etcd import Lock as EtcdLock
from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerMixin
from kombu.utils.debug import setup_logging
from optscale_client.config_client.client import Client as ConfigClient
from optscale_client.rest_api_client.client_v2 import Client as RestClient
from risp.risp_worker.migrator import Migrator
from risp.risp_worker.processors.factory import RispProcessors


LOG = logging.getLogger(__name__)

QUEUE_NAME = 'risp-task'
EXCHANGE_NAME = 'risp-tasks'
TASK_EXCHANGE = Exchange(EXCHANGE_NAME, type='direct')
TASK_QUEUE = Queue(QUEUE_NAME, TASK_EXCHANGE, routing_key=QUEUE_NAME)


class RISPWorker(ConsumerMixin):
    def __init__(self, connection, config_client):
        self.connection = connection
        self.running = True
        self.config_client = config_client
        self._rest_cl = None
        self.thread = Thread(target=self.heartbeat)
        self.thread.start()

    @property
    def rest_cl(self):
        if self._rest_cl is None:
            self._rest_cl = RestClient(
                url=self.config_client.restapi_url(),
                secret=self.config_client.cluster_secret(),
                verify=False)
        return self._rest_cl

    def get_consumers(self, consumer, channel):
        return [consumer(queues=[TASK_QUEUE], accept=['json'],
                         callbacks=[self.process_task], prefetch_count=10)]

    def _process_task(self, body):
        cloud_account_id = body.get('cloud_account_id')
        cloud_type = body.get('cloud_type')
        code, response = self.rest_cl.risp_processing_task_list(
            cloud_account_id)
        LOG.info('Task list response: %s', response)
        if code != 200:
            raise ValueError(f'Task list response is invalid: {response}')
        processor = RispProcessors.get_processor(cloud_type)(
            self.config_client)
        for task in response['risp_processing_tasks']:
            start_date = datetime.fromtimestamp(task['start_date']).replace(
                tzinfo=timezone.utc)
            end_date = datetime.fromtimestamp(task['end_date']).replace(
                tzinfo=timezone.utc)
            processor.process_task(cloud_account_id, start_date, end_date)
            self.rest_cl.risp_processing_task_delete(task['id'])

    def process_task(self, body, message):
        try:
            LOG.info('Processing task: %s', body)
            self._process_task(body)
        except Exception as exc:
            LOG.exception('Task processing failed for cloud account %s '
                          'with exception: %s',
                          body.get('cloud_account_id'), str(exc))
        LOG.info('Task is finished')
        message.ack()

    def heartbeat(self):
        while self.running:
            self.connection.heartbeat_check()
            time.sleep(1)


if __name__ == '__main__':
    urllib3.disable_warnings(
        category=urllib3.exceptions.InsecureRequestWarning)
    debug = os.environ.get('DEBUG', False)
    log_level = 'DEBUG' if debug else 'INFO'
    setup_logging(loglevel=log_level, loggers=[''])

    config_cl = ConfigClient(
        host=os.environ.get('HX_ETCD_HOST'),
        port=int(os.environ.get('HX_ETCD_PORT')),
    )
    config_cl.wait_configured()
    conn_str = 'amqp://{user}:{pass}@{host}:{port}'.format(
        **config_cl.read_branch('/rabbit'))
    with Connection(conn_str) as conn:
        try:
            migrator = Migrator(config_cl)
            with EtcdLock(config_cl, 'risp_migrations'):
                migrator.migrate()
            worker = RISPWorker(conn, config_cl)
            worker.run()
        except KeyboardInterrupt:
            worker.running = False
            worker.thread.join()
            LOG.info('Shutdown received')
