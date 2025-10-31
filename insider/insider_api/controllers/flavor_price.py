import logging
import re
from datetime import timedelta
from pymongo import MongoClient, UpdateOne
from requests.exceptions import HTTPError

from insider.insider_api.controllers.base import (
    BaseController, BaseAsyncControllerWrapper)
from insider.insider_api.exceptions import Err

from tools.cloud_adapter.clouds.alibaba import Alibaba
from tools.cloud_adapter.clouds.aws import Aws
from tools.cloud_adapter.clouds.azure import Azure
from tools.cloud_adapter.clouds.gcp import Gcp
from tools.optscale_exceptions.common_exc import WrongArgumentsException
from botocore.exceptions import ClientError as AwsClientError
from insider.insider_api.utils import handle_credentials_error
from tools.optscale_time import utcnow

LOG = logging.getLogger(__name__)


class BaseProvider:
    def __init__(self, config_cl, rest_client=None):
        self._config_cl = config_cl
        self._mongo_client = None
        self.rest_client = rest_client
        self._cloud_adapter = None
        self.cloud_account_id = None

    @property
    def mongo_client(self):
        if not self._mongo_client:
            mongo_params = self._config_cl.mongo_params()
            self._mongo_client = MongoClient(mongo_params[0])
        return self._mongo_client

    @property
    def prices_collection(self):
        raise NotImplementedError()

    @property
    def cloud_adapter(self):
        raise NotImplementedError()

    def _load_flavor_prices(self, region, flavor, os_type, preinstalled,
                            quantity, billing_method, currency='USD',
                            currency_conversion_rate=None):
        raise NotImplementedError()

    def _load_family_prices(self, instance_family, region, os_type, currency):
        raise NotImplementedError()

    def _flavor_format(self, price_infos, region, os_type, currency="USD"):
        raise NotImplementedError()

    def _flavor_family_format(self, price_infos, instance_family, region,
                              os_type):
        raise NotImplementedError()

    def get_flavor_prices(self, region, flavor, os_type, preinstalled=None,
                          billing_method=None, quantity=None, currency='USD',
                          currency_conversion_rate=None,
                          cloud_account_id=None):
        if cloud_account_id:
            self.cloud_account_id = cloud_account_id
        price_infos = self._load_flavor_prices(
            region, flavor, os_type=os_type, preinstalled=preinstalled,
            billing_method=billing_method, quantity=quantity,
            currency=currency,
            currency_conversion_rate=currency_conversion_rate)
        return self._flavor_format(price_infos, region, os_type, currency)

    def get_family_prices(self, instance_family, region, os_type, currency):
        price_infos = self._load_family_prices(
            instance_family, region, os_type, currency)
        return self._flavor_family_format(
            price_infos, instance_family, region, os_type)


class AwsProvider(BaseProvider):
    def __init__(self, config_cl, rest_client=None):
        super().__init__(config_cl, rest_client)
        self.os_map = {
            'rhel': 'RHEL',
            'windows': 'Windows',
            'suse': 'SUSE',
            'linux': 'Linux'
        }
        self.preinstalled_map = {
            'sql std': 'SQL Std',
            'sql web': 'SQL Web',
            'sql ent': 'SQL Ent'
        }
        self._region_map = None

    @property
    def cloud_adapter(self):
        if self._cloud_adapter is None:
            config = self._config_cl.read_branch('/service_credentials/aws')
            self._cloud_adapter = Aws(config)
        return self._cloud_adapter

    @property
    def region_map(self):
        if self._region_map is None:
            self._region_map = {}
            coord_map = self.cloud_adapter.get_regions_coordinates()
            for region, data in coord_map.items():
                region_code = data.get('alias') or data.get('name')
                if region_code:
                    self._region_map[region] = region_code
        return self._region_map

    @property
    def prices_collection(self):
        return self.mongo_client.restapi.aws_prices

    @handle_credentials_error(AwsClientError)
    def _load_flavor_prices(self, region, flavor, os_type, preinstalled=None,
                            **_kwargs):
        location = self.region_map.get(region)
        if not location:
            raise WrongArgumentsException(Err.OI0012, [region])
        operating_system = self.os_map.get(os_type.lower())
        if not operating_system:
            raise WrongArgumentsException(Err.OI0015, [os_type])
        software = self.preinstalled_map.get(
            preinstalled.lower(), 'NA') if preinstalled else 'NA'

        now = utcnow()
        query = {
            'instanceType': flavor,
            'location': location,
            'operatingSystem': operating_system,
            'tenancy': 'Shared',
            'preInstalledSw': software,
            'capacitystatus': 'Used',
            'licenseModel': 'No License required',
            'updated_at': {'$gte': now - timedelta(days=60)}
        }
        price_infos = list(self.prices_collection.find(query))
        if not price_infos:
            query.pop('updated_at', None)
            price_infos = self.cloud_adapter.get_prices(query)
            updates = []
            for price_info in price_infos:
                price_info['updated_at'] = now
                updates.append(UpdateOne(
                    filter={'sku': price_info['sku']},
                    update={'$set': price_info},
                    upsert=True,
                ))
            if updates:
                self.prices_collection.bulk_write(updates)
        return price_infos

    def _load_family_prices(self, instance_family, region, os_type, currency):
        location = self.region_map.get(region)
        if not location:
            raise WrongArgumentsException(Err.OI0012, [region])
        operating_system = self.os_map.get(os_type.lower())
        if not operating_system:
            raise WrongArgumentsException(Err.OI0015, [os_type])

        # TODO: Add currency support
        now = utcnow()
        regex = re.compile(f"{instance_family}\\.", re.IGNORECASE)
        query = {
            'instanceType': regex,
            'location': location,
            'operatingSystem': operating_system,
            'tenancy': 'Shared',
            'preInstalledSw': 'NA',
            'capacitystatus': 'Used',
            'licenseModel': 'No License required',
            'updated_at': {'$gte': now - timedelta(days=60)}
        }
        price_infos = list(self.prices_collection.find(query))
        if not price_infos:
            query.pop('updated_at', None)
            query.pop('instanceType', None)
            res = self.cloud_adapter.get_prices(query)
            updates = []
            for price_info in res:
                price_info['updated_at'] = now
                if regex.match(price_info.get('instanceType')):
                    price_infos.append(price_info)
                updates.append(UpdateOne(
                    filter={'sku': price_info['sku']},
                    update={'$set': price_info},
                    upsert=True,
                ))
            if updates:
                self.prices_collection.bulk_write(updates)
        return price_infos

    def _validate_price_info(self, price_info):
        if price_info['price_unit'].lower() not in {'hours', 'hrs'}:
            LOG.warning('Unusual price unit found. Price - %s', price_info)
            return False
        return True

    def _flavor_format(self, price_infos, region, os_type, currency='USD'):
        res = []
        price_unit = '1 hour'
        for price_info in price_infos:
            if not self._validate_price_info(price_info):
                continue
            currency, price = next(iter(price_info['price'].items()))
            res.append({
                'price': float(price),
                'region': region,
                'flavor': price_info['instanceType'],
                'operating_system': os_type.lower(),
                'price_unit': price_unit,
                'currency': currency
            })
        return res

    def _flavor_family_format(self, price_infos, instance_family, region,
                              os_type):
        res = []
        price_unit = '1 hour'
        for price_info in price_infos:
            if not self._validate_price_info(price_info):
                continue
            currency, price = next(iter(price_info['price'].items()))
            cpu = price_info.get('vcpu')
            if cpu is not None:
                cpu = int(cpu)
            ram = price_info.get('memory')
            if ram is not None:
                ram = int(float(ram.split(' ')[0]) * 1024)
            gpu = price_info.get('gpu')
            if gpu is not None:
                gpu = int(gpu)
            res.append({
                'price': float(price),
                'region': region,
                'instance_family': instance_family,
                'instance_type': price_info['instanceType'],
                'operating_system': os_type.lower(),
                'price_unit': price_unit,
                'currency': currency,
                'cpu': cpu,
                'ram': ram,
                'gpu': gpu
            })
        return res


class AzureProvider(BaseProvider):
    @property
    def prices_collection(self):
        return self.mongo_client.insider.azure_prices

    @property
    def cloud_adapter(self):
        if self._cloud_adapter is None:
            config = self._config_cl.read_branch('/service_credentials/azure')
            self._cloud_adapter = Azure(config)
        return self._cloud_adapter

    @property
    def discoveries_collection(self):
        return self.mongo_client.insider.discoveries

    def _load_flavor_prices(self, region, flavor, os_type, currency='USD',
                            **_kwargs):
        regions = set(self.cloud_adapter.get_regions_coordinates())
        if region not in regions:
            raise WrongArgumentsException(Err.OI0012, [region])
        operating_system = os_type.lower()
        if operating_system not in {'windows', 'linux'}:
            raise WrongArgumentsException(Err.OI0015, [os_type])

        now = utcnow()
        product_name_regex = "Windows$" if operating_system == 'windows' else ".*(?<!Windows)$"
        query = {
            'type': 'Consumption',
            'serviceName': 'Virtual Machines',
            'armSkuName': re.compile(flavor, re.IGNORECASE),
            'armRegionName': region,
            '$or': [
                {'effectiveEndDate': {'$gte': now}},
                {'effectiveEndDate': {'$exists': False}}
            ],
            'productName': {'$regex': product_name_regex},
            'skuName': {'$regex': ".*[^Spot][^Priority]$"},
            'currencyCode': currency
        }
        return list(self.prices_collection.find(query).sort(
            [('last_seen', -1)]).limit(1))

    def _flavor_format(self, price_infos, region, os_type, currency='USD'):
        res = []
        for price_info in price_infos:
            res.append({
                'price': price_info['unitPrice'],
                'region': price_info['armRegionName'],
                'flavor': price_info['armSkuName'],
                'operating_system': os_type.lower(),
                'price_unit': price_info['unitOfMeasure'].lower(),
                'currency': price_info['currencyCode']
            })
        return res


class AlibabaProvider(BaseProvider):
    @property
    def prices_collection(self):
        return self.mongo_client.insider.alibaba_prices

    @property
    def cloud_adapter(self):
        if self._cloud_adapter is None:
            config = self._config_cl.read_branch(
                '/service_credentials/alibaba')
            if self.cloud_account_id:
                try:
                    _, cloud_acc = self.rest_client.cloud_account_get(
                        self.cloud_account_id)
                except HTTPError:
                    raise WrongArgumentsException(Err.OI0008, ['cloud_account_id'])
                config = cloud_acc['config']
            self._cloud_adapter = Alibaba(config)
        return self._cloud_adapter

    def _load_flavor_prices(self, region, flavor, os_type='linux',
                            billing_method='pay_as_you_go', quantity=1,
                            currency='USD', **_kwargs):
        now = utcnow()
        query = {
            'region': region,
            'flavor': flavor,
            'quantity': quantity,
            'billing_method': billing_method,
            'updated_at': {'$gte': now - timedelta(days=60)},
            'cloud_account_id': self.cloud_account_id
        }
        price_infos = list(self.prices_collection.find(query))
        if not price_infos:
            if region not in self.cloud_adapter.get_regions_coordinates():
                raise WrongArgumentsException(Err.OI0012, [region])
            prices = self.cloud_adapter.get_flavor_prices(
                [flavor], region, os_type=os_type,
                billing_method=billing_method, quantity=quantity,
                price_only=False)
            updates = []
            for flavor, price_info in prices.items():
                price_info['updated_at'] = now
                price_info['flavor'] = flavor
                price_info['region'] = region
                price_info['quantity'] = quantity
                price_info['cloud_account_id'] = self.cloud_account_id
                updates.append(UpdateOne(
                    filter={'flavor': flavor, 'region': region,
                            'quantity': quantity,
                            'billing_method': price_info['billing_method'],
                            'cloud_account_id': self.cloud_account_id},
                    update={'$set': price_info},
                    upsert=True,
                ))
                price_infos.append(price_info)
            if updates:
                self.prices_collection.bulk_write(updates)
        return price_infos

    def _flavor_format(self, price_infos, region, os_type, currency='USD'):
        result = []
        price_unit = '1 hour'
        for price_info in price_infos:
            result.append({
                'price': float(price_info['CostAfterDiscount']),
                'region': region,
                'flavor': price_info['flavor'],
                'operating_system': os_type,
                'price_unit': price_unit,
                'currency': currency
            })
        return result


class GcpProvider(BaseProvider):
    @property
    def prices_collection(self):
        return self.mongo_client.insider.gcp_prices

    @property
    def cloud_adapter(self):
        if self._cloud_adapter is None:
            config = self._config_cl.read_branch('/service_credentials/gcp')
            if self.cloud_account_id:
                try:
                    _, cloud_acc = self.rest_client.cloud_account_get(
                        self.cloud_account_id)
                except HTTPError:
                    raise WrongArgumentsException(Err.OI0008, ['cloud_account_id'])
                if 'pricing_data' in cloud_acc['config']:
                    config = cloud_acc['config']
            self._cloud_adapter = Gcp(config)
        return self._cloud_adapter

    def _load_flavor_prices(
            self, region, flavor, currency_conversion_rate=None, **_kwargs):
        now = utcnow()
        if region not in self.cloud_adapter.get_regions_coordinates():
            raise WrongArgumentsException(Err.OI0008, ['region'])
        query = {
            'region': region,
            'flavor': flavor,
            'updated_at': {'$gte': now - timedelta(days=60)}
        }
        price_infos = list(self.prices_collection.find(query))
        use_usd_price = False
        if currency_conversion_rate:
            use_usd_price = True
        if not price_infos:
            prices = self.cloud_adapter.get_instance_types_priced(
                region, use_usd_price)
            updates = []
            for flavor_name, price_info in prices.items():
                price_info['updated_at'] = now
                price_info['flavor'] = flavor_name
                price_info['region'] = region
                updates.append(UpdateOne(
                    filter={'flavor': flavor_name, 'region': region},
                    update={'$set': price_info},
                    upsert=True,
                ))
                price_infos.append(price_info)
            if updates:
                self.prices_collection.bulk_write(updates)
        flavor_prices = list(filter(lambda x: x['flavor'] == flavor,
                                    price_infos))
        if currency_conversion_rate:
            for flavor in flavor_prices:
                flavor['price'] = flavor['price'] * currency_conversion_rate
        return flavor_prices

    def _flavor_format(self, price_infos, region, os_type, currency='USD'):
        result = []
        price_unit = '1 hour'
        for price_info in price_infos:
            result.append({
                'price': price_info['price'],
                'region': region,
                'flavor': price_info['flavor'],
                'operating_system': os_type,
                'price_unit': price_unit,
                'currency': currency
            })
        return result


class PricesProvider:
    __modules__ = {
        'azure': AzureProvider,
        'aws': AwsProvider,
        'alibaba': AlibabaProvider,
        'gcp': GcpProvider
    }

    @staticmethod
    def get_provider(cloud_type):
        provider = PricesProvider.__modules__.get(cloud_type)
        if not provider:
            raise WrongArgumentsException(Err.OI0010, [cloud_type])
        return provider


class FlavorPriceController(BaseController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def supported_cloud_types(self):
        return ['alibaba', 'azure', 'aws', 'gcp']

    @property
    def required_params(self):
        return [('cloud_type', str), ('region', str), ('flavor', str),
                ('os_type', str)]

    def validate_parameters(self, **params):
        missing_required = [
            p for p, _ in self.required_params if params.get(p) is None
        ]
        if missing_required:
            message = ', '.join(missing_required)
            raise WrongArgumentsException(Err.OI0011, [message])

        for param, param_type in self.required_params:
            value = params.get(param)
            if value is not None and not isinstance(value, param_type):
                raise WrongArgumentsException(Err.OI0008, [param])
        cloud_type = params.get('cloud_type')
        if cloud_type not in self.supported_cloud_types:
            raise WrongArgumentsException(Err.OI0010, [cloud_type])
        if cloud_type == 'alibaba':
            for p in ['quantity', 'billing_method']:
                if params.get(p) is None:
                    raise WrongArgumentsException(Err.OI0011, [p])

    def get(self, **kwargs):
        self.validate_parameters(**kwargs)
        cloud_type = kwargs['cloud_type']
        region = kwargs['region']
        os_type = kwargs['os_type']
        flavor = kwargs['flavor']
        preinstalled = kwargs.get('preinstalled')
        quantity = kwargs.get('quantity')
        billing_method = kwargs.get('billing_method')
        currency = kwargs.get('currency')
        currency_conversion_rate = kwargs.get('currency_conversion_rate')
        cloud_account_id = kwargs.get('cloud_account_id')
        provider = PricesProvider.get_provider(cloud_type)
        return provider(self._config, self.rest_client).get_flavor_prices(
            region, flavor, os_type, preinstalled, billing_method, quantity,
            currency, currency_conversion_rate, cloud_account_id)


class FlavorPriceAsyncController(BaseAsyncControllerWrapper):
    def _get_controller_class(self):
        return FlavorPriceController


class FamilyPriceController(FlavorPriceController):
    @property
    def supported_cloud_types(self):
        return ['aws']

    @property
    def required_params(self):
        return [('cloud_type', str), ('region', str), ('instance_family', str)]

    def get(self, **kwargs):
        self.validate_parameters(**kwargs)
        cloud_type = kwargs['cloud_type']
        instance_family = kwargs['instance_family']
        region = kwargs['region']
        os_type = kwargs.get('os_type') or 'Linux'
        currency = kwargs.get('currency') or 'USD'
        provider = PricesProvider.get_provider(cloud_type)
        return provider(self._config, self.rest_client).get_family_prices(
            instance_family=instance_family, region=region, os_type=os_type,
            currency=currency
        )


class FamilyPriceAsyncController(BaseAsyncControllerWrapper):
    def _get_controller_class(self):
        return FamilyPriceController
