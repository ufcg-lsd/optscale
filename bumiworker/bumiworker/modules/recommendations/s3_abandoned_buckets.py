import logging
from collections import OrderedDict
from bumiworker.bumiworker.modules.abandoned_base import S3AbandonedBucketsBase


LOG = logging.getLogger(__name__)

DEFAULT_DAYS_THRESHOLD = 30
GET_OBJECT_KEY = 'get_object_count'
PUT_OBJECT_KEY = 'put_object_count'


class S3AbandonedBuckets(S3AbandonedBucketsBase):
    SUPPORTED_CLOUD_TYPES = [
        'aws_cnr'
    ]

    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = OrderedDict({
            'days_threshold': {
                'default': DEFAULT_DAYS_THRESHOLD},
            'excluded_pools': {
                'default': {},
                'clean_func': self.clean_excluded_pools,
            },
            'skip_cloud_accounts': {'default': []}
        })

    def get_metric_threshold_map(self):
        # Buckets are considered abandoned if both GetObject and PutObject
        # operations are zero (no read or write activity)
        return {
            GET_OBJECT_KEY: False,
            PUT_OBJECT_KEY: False
        }

    def _get_data_size_request_metrics(self, cloud_account_id,
                                       cloud_resource_ids, start_date,
                                       days_threshold):
        # Query for GetObject and PutObject operations in API Request product family
        target_operations = ['GetObject', 'PutObject']
        api_request_pipeline = [
            {
                '$match': {
                    '$and': [
                        {'resource_id': {'$in': cloud_resource_ids}},
                        {'cloud_account_id': cloud_account_id},
                        {'start_date': {'$gte': start_date}},
                        {'product/productFamily': 'API Request'},
                        {'lineItem/Operation': {'$in': target_operations}}
                    ]
                }
            },
            {
                '$group': {
                    '_id': {
                        '_id': '$resource_id',
                        'operation': '$lineItem/Operation'
                    },
                    'total_usage': {
                        '$sum': '$lineItem/UsageAmount'
                    }
                }
            }
        ]
        api_requests = self.mongo_client.restapi.raw_expenses.aggregate(
            api_request_pipeline)
        resource_meter_value = {}
        # Initialize all resources with no recorded activity
        for res_id in cloud_resource_ids:
            resource_meter_value[res_id] = {
                GET_OBJECT_KEY: False,
                PUT_OBJECT_KEY: False
            }
        # Aggregate operation usage (already summed by MongoDB)
        for api_request in api_requests:
            cloud_resource_id = api_request['_id']['_id']
            operation = api_request['_id']['operation']
            total_sum = int(api_request['total_usage'])
            has_usage = bool(total_sum)
            if operation == 'GetObject':
                resource_meter_value[cloud_resource_id][
                    GET_OBJECT_KEY] = has_usage
            elif operation == 'PutObject':
                resource_meter_value[cloud_resource_id][
                    PUT_OBJECT_KEY] = has_usage
        return resource_meter_value

    @staticmethod
    def metrics_result(data_req_map):
        return {
            'get_object_count': data_req_map.get(GET_OBJECT_KEY, False),
            'put_object_count': data_req_map.get(PUT_OBJECT_KEY, False),
        }


def main(organization_id, config_client, created_at, **kwargs):
    return S3AbandonedBuckets(
        organization_id, config_client, created_at).get()


def get_module_email_name():
    return 'Abandoned Amazon S3 buckets'
