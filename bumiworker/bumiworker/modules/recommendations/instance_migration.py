import logging
from collections import defaultdict, OrderedDict
from datetime import timedelta
from pymongo import UpdateOne

from tools.cloud_adapter.clouds.aws import Aws
from tools.cloud_adapter.clouds.alibaba import Alibaba
from tools.optscale_time import utcnow
from bumiworker.bumiworker.modules.base import ModuleBase


HOURS_IN_MONTH = 30 * 24
SUPPORTED_CLOUD_TYPES = [
    'aws_cnr',
    'alibaba_cnr'
]

ALIBABA_REGION_MAP = {
    'us': ['US (Silicon Valley)', 'US (Virginia)'],
    'eu': ['Germany (Frankfurt)', 'UK (London)'],
    'cn': ['China (Qingdao)', 'China (Beijing)', 'China (Zhangjiakou)',
           'China (Hohhot)', 'China (Ulanqab)', 'China (Hangzhou)',
           'China (Shanghai)', 'China (Shenzhen)', 'China (Heyuan)',
           'China (Guangzhou)', 'China (Chengdu)',
           'China (Nanjing - Local Region)'],
    'ap': ['China (Hong Kong)', 'Japan (Tokyo)', 'Singapore',
           'Malaysia (Kuala Lumpur)', 'Indonesia (Jakarta)',
           'Thailand (Bangkok)', 'Philippines (Manila)',
           'South Korea (Seoul)'],
    'me': ['UAE (Dubai)']}


AWS_REGION_MAP = {
    'af': ['af-south-1'],
    'ap': ['ap-east-1', 'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
           'ap-south-1', 'ap-south-2', 'ap-southeast-1',
           'ap-southeast-2', 'ap-southeast-3', 'ap-southeast-4',
           'ap-southeast-5', 'ap-southeast-7'],
    'ca': ['ca-central-1', 'ca-west-1'],
    'eu': ['eu-central-1', 'eu-central-2', 'eu-west-1', 'eu-west-2',
           'eu-west-3', 'eu-south-1', 'eu-south-2', 'eu-north-1'],
    'il': ['il-central-1'],
    'mx': ['mx-central-1'],
    'me': ['me-south-1', 'me-central-1'],
    'sa': ['sa-east-1'],
    'us': ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2'],
}
AWS_SKU_INDEX = 'AwsSkuIndex'
unique_sku_fields = [
    'location',
    'locationType',
    'usagetype',
    'price_unit',
    'price',
    'sku',
    'updated_at',
    '_id',
    'regionCode'
]
LOG = logging.getLogger(__name__)


class InstanceMigration(ModuleBase):
    def __init__(self, organization_id, config_client, created_at):
        super().__init__(organization_id, config_client, created_at)
        self.option_ordered_map = OrderedDict({
            'excluded_pools': {
                'default': {},
                'clean_func': self.clean_excluded_pools,
            },
            'skip_cloud_accounts': {'default': []}
        })

    @property
    def aws_prices(self):
        return self.mongo_client.restapi.aws_prices

    def check_index_in_prices_collection(self):
        existing_indexes = [
            x['name'] for x in self.aws_prices.list_indexes()
        ]
        if AWS_SKU_INDEX not in existing_indexes:
            self.aws_prices.create_index(
                [('sku', 1)],
                name=AWS_SKU_INDEX,
            )

    @property
    def aws(self):
        config = self.config_cl.read_branch('/service_credentials/aws')
        return Aws(config)

    def get_similar_skus(self, resource_id, sku):
        def get_skus_from_cloud(sku):
            similar_skus = self.aws.get_similar_sku_prices(sku)
            updates = []
            for sku in similar_skus:
                sku['updated_at'] = utcnow()
                updates.append(UpdateOne(
                    filter={'sku': sku['sku']},
                    update={'$set': sku},
                    upsert=True,
                ))
            self.aws_prices.bulk_write(updates)
            return similar_skus

        sku_dict = list(self.aws_prices.find({
            'sku': sku,
            'updated_at': {'$gte': utcnow() - timedelta(days=60)}
        }))
        if sku_dict:
            LOG.info('Found SKU %s for instance %s in DB', sku, resource_id)
            sku_dict = sku_dict[0]
            for field in unique_sku_fields:
                sku_dict.pop(field, None)

            similar_skus = list(self.aws_prices.find(sku_dict))
            if len(similar_skus) == 1:
                LOG.info('Only current SKU %s for instance %s found in db, '
                         'taking from cloud', sku, resource_id)
                similar_skus = get_skus_from_cloud(sku)
        else:
            LOG.info('SKU %s for instance %s not found in db, '
                     'taking from cloud', sku, resource_id)
            similar_skus = get_skus_from_cloud(sku)
        return similar_skus

    def get_aws_recommendations(self, instance_map, cloud_account_map,
                                excluded_pools):
        result = []
        coordinates = self.aws.get_regions_coordinates()
        aws_region_names_to_codes = {}
        for region_id, coord in coordinates.items():
            if 'name' in coord:
                aws_region_names_to_codes[coord['name']] = region_id
        res = self.mongo_client.restapi.raw_expenses.aggregate([
            {'$match': {
                '$and': [
                    {'box_usage': True},
                    {'resource_id': {'$in': list(instance_map.keys())}},
                    {'cloud_account_id': {
                        '$in': list(cloud_account_map.keys())}},
                    {'start_date': {
                        '$gte': utcnow() - timedelta(days=10)}},
                    {'cost': {'$ne': 0}},
                ]
            }},
            {'$sort': {'end_date': 1}},
            {'$group': {
                '_id': {'resource_id': '$resource_id'},
                'sku': {'$last': '$product/sku'},
                'flavor': {'$last': '$product/instanceType'}
            }}
        ])
        for sku_info in res:
            resource_id = sku_info['_id']['resource_id']
            instance_info = instance_map[resource_id]
            if instance_info['meta']['flavor'] != sku_info['flavor']:
                continue
            cloud_account_id = instance_info['cloud_account_id']

            similar_skus = self.get_similar_skus(resource_id, sku_info['sku'])

            region_prefix = instance_info['region'].split('-')[0]
            similar_regions = AWS_REGION_MAP.get(region_prefix, [])
            similar_from_regions = {}
            for sku_dict in similar_skus:
                _index = sku_dict['location'].index('(')
                location_detailed = sku_dict['location'][_index:]
                for test_region in aws_region_names_to_codes:
                    if location_detailed in test_region:
                        region = aws_region_names_to_codes.get(test_region)
                        break
                else:
                    continue

                if not region or region not in similar_regions:
                    continue
                if sku_dict['price_unit'] != 'Hrs':
                    LOG.warning('Unusual price unit found, skipping: %s',
                                sku_dict['price_unit'])
                    continue
                monthly_price = float(
                    sku_dict['price'].get('USD')) * HOURS_IN_MONTH
                sku_dict['monthly_price'] = monthly_price
                sku_dict['region'] = region
                similar_from_regions[sku_dict['sku']] = sku_dict

            cheapest_sku = min(similar_from_regions.values(),
                               key=lambda x: x['monthly_price'],
                               default=None)
            if cheapest_sku is None or cheapest_sku['sku'] == sku_info['sku']:
                continue

            current_sku = similar_from_regions[sku_info['sku']]
            saving = current_sku['monthly_price'] - cheapest_sku[
                'monthly_price']
            if not saving:
                continue

            result.append({
                'saving': saving,
                'flavor': instance_info['meta']['flavor'],
                'current_region': instance_info['region'],
                'recommended_region': cheapest_sku['region'],
                'cloud_resource_id': instance_info['cloud_resource_id'],
                'resource_name': instance_info.get('name'),
                'resource_id': instance_info['resource_id'],
                'cloud_account_id': cloud_account_id,
                'cloud_type': cloud_account_map[cloud_account_id].get('type'),
                'cloud_account_name':
                    cloud_account_map[cloud_account_id].get('name'),
                'is_excluded': instance_info.get('pool_id') in excluded_pools,
            })
        return result

    @staticmethod
    def _get_nearby_alibaba_regions(region):
        for _, regions_list in ALIBABA_REGION_MAP.items():
            if region in regions_list:
                return regions_list

    def get_alibaba_recommendations(self, alibaba_instance_map,
                                    cloud_account_map, excluded_pools):
        result = []
        cloud_acc_flavors = defaultdict(lambda: defaultdict(
            lambda: defaultdict(set)))
        for resource in alibaba_instance_map.values():
            cloud_account_id = resource['cloud_account_id']
            region = resource['region']
            flavor = resource['meta']['flavor']
            nearby_regions = self._get_nearby_alibaba_regions(region)
            cloud_acc_flavors[cloud_account_id][region][flavor].update(
                nearby_regions)

        available_flavors = {}
        prices = {}
        for cloud_account_id, data in cloud_acc_flavors.items():
            cloud_account = cloud_account_map.get(cloud_account_id)
            if not cloud_account:
                continue
            alibaba = Alibaba(cloud_account['config'])
            for region, flavor_data in data.items():
                flavors = alibaba.get_available_flavors(region)
                available_flavors[region] = [x for x in flavors
                                             if x in list(flavor_data)]
                try:
                    prices[region] = alibaba.get_flavor_prices(flavors, region)
                except ValueError as exc:
                    LOG.info("Unable to find flavor prices: %s", exc)
                    prices[region] = {}
                    continue
                for flav, price in prices[region].items():
                    prices[region][flav] = price * HOURS_IN_MONTH

        for resource in alibaba_instance_map.values():
            flavor = resource['meta']['flavor']
            region = resource['region']
            flavor_region_prices = {
                region: prices[flavor] for region, prices in prices.items()
                if flavor in prices
            }
            if not flavor_region_prices or region not in flavor_region_prices:
                continue
            cheapest_region = min(flavor_region_prices.keys(),
                                  key=lambda x: flavor_region_prices[x])
            if cheapest_region != region:
                curr_price = flavor_region_prices.get(region)
                min_price = flavor_region_prices.get(cheapest_region)
                saving = curr_price - min_price
                if saving > 0:
                    result.append({
                        'saving': saving,
                        'flavor': resource['meta']['flavor'],
                        'current_region': resource['region'],
                        'recommended_region': cheapest_region,
                        'cloud_resource_id': resource['cloud_resource_id'],
                        'resource_name': resource.get('name'),
                        'resource_id': resource['resource_id'],
                        'cloud_account_id': resource['cloud_account_id'],
                        'cloud_type': cloud_account_map[
                            resource['cloud_account_id']].get('type'),
                        'cloud_account_name': cloud_account_map[
                            resource['cloud_account_id']].get('name'),
                        'is_excluded': resource.get(
                            'pool_id') in excluded_pools,
                    })
        return result

    def _get(self):
        (excluded_pools, skip_cloud_accounts) = self.get_options_values()
        self.check_index_in_prices_collection()

        cloud_account_map = self.get_cloud_accounts(
            SUPPORTED_CLOUD_TYPES, skip_cloud_accounts)

        _, response = self.rest_client.cloud_resources_discover(
            self.organization_id, 'instance')

        aws_instance_map = {}
        alibaba_instance_map = {}
        clouds = {'aws_cnr': [AWS_REGION_MAP, aws_instance_map],
                  'alibaba_cnr': [ALIBABA_REGION_MAP, alibaba_instance_map]}
        for instance in response['data']:
            if instance['meta']['spotted']:
                continue
            if instance['cloud_account_id'] not in cloud_account_map.keys():
                continue
            cloud_acc = cloud_account_map.get(instance['cloud_account_id'])
            if not cloud_acc:
                continue
            cloud_type = cloud_acc['type']
            if instance['region'] not in sum(
                    clouds.get(cloud_type)[0].values(), []):
                continue
            else:
                clouds[cloud_type][1][instance['cloud_resource_id']] = instance

        aws_result = []
        if aws_instance_map:
            aws_result = self.get_aws_recommendations(
                aws_instance_map, cloud_account_map, excluded_pools)

        alibaba_result = []
        if alibaba_instance_map:
            alibaba_result = self.get_alibaba_recommendations(
                alibaba_instance_map, cloud_account_map, excluded_pools)
        return aws_result + alibaba_result


def main(organization_id, config_client, created_at, **kwargs):
    return InstanceMigration(
        organization_id, config_client, created_at).get()


def get_module_email_name():
    return 'Instances with migration opportunities'
