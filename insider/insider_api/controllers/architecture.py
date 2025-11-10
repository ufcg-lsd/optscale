import logging
from pymongo import UpdateOne
from tools.cloud_adapter.clouds.alibaba import Alibaba
from tools.cloud_adapter.clouds.aws import Aws
from tools.cloud_adapter.clouds.azure import Azure
from insider.insider_api.controllers.base import (
    BaseController, BaseAsyncControllerWrapper, CachedThreadPoolExecutor,
    CachedCloudCaller
)

ARCH_ALIASES = {
    'arm': 'arm64',
    'x86': 'x86_64',
    'x64': 'x86_64',
}
LOG = logging.getLogger(__name__)


class ArchitectureController(BaseController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.caller = CachedCloudCaller(self.mongo_client)
        self.cloud_account_id = None
        self._aws = None
        self._azure = None
        self._alibaba = None

    @property
    def architectures_collection(self):
        return self.mongo_client.insider.architectures

    @property
    def aws(self):
        if self._aws is None:
            config = self.get_service_credentials('aws')
            if self.cloud_account_id:
                cloud_acc = self.get_cloud_account(self.cloud_account_id)
                config = cloud_acc['config']
            self._aws = Aws(config)
        return self._aws

    @property
    def azure(self):
        if self._azure is None:
            config = self.get_service_credentials('azure')
            if self.cloud_account_id:
                cloud_acc = self.get_cloud_account(self.cloud_account_id)
                config = cloud_acc['config']
            self._azure = Azure(config)
        return self._azure

    @property
    def alibaba(self):
        if self._alibaba is None:
            config = self.get_service_credentials('alibaba')
            if self.cloud_account_id:
                cloud_acc = self.get_cloud_account(self.cloud_account_id)
                config = cloud_acc['config']
            self._alibaba = Alibaba(config)
        return self._alibaba

    def _get_aws_flavors(self, region):
        return self.aws.get_all_instance_types(region=region)

    def _get_azure_flavors(self):
        return self.azure.get_flavors_info(architecture=True)

    def _get_alibaba_flavors(self, region):
        return self.alibaba.get_all_flavors(region=region)

    def get_aws_architectures(self, region):
        instance_types = self._get_aws_flavors(region)
        result = []
        for r in instance_types:
            i_type = r.get('InstanceType')
            archs = r.get('ProcessorInfo', {}).get('SupportedArchitectures', [])
            if i_type and archs:
                for arch in archs:
                    arch = arch.lower()
                    result.append({
                        'flavor': i_type,
                        'architecture': ARCH_ALIASES.get(arch, arch)
                    })
        return result

    def get_azure_architectures(self, region):
        flavors = self._get_azure_flavors()
        result = []
        for flavor in flavors.values():
            name = flavor.get('name')
            arch = flavor.get('architecture')
            if name and arch:
                arch = arch.lower()
                result.append({
                    'flavor': name,
                    'architecture': ARCH_ALIASES.get(arch, arch)
                })
        return result

    def get_alibaba_architectures(self, region):
        res = self._get_alibaba_flavors(region=region)
        result = []
        for k, v in res.items():
            arch = v.get('CpuArchitecture')
            if k and arch:
                arch = arch.lower()
                result.append({
                    'flavor': k,
                    'architecture': ARCH_ALIASES.get(arch, arch)
                })
        return result

    def get(self, **kwargs):
        cloud_type = kwargs['cloud_type']
        flavor = kwargs['flavor'].lower()
        cloud_account_id = kwargs.get('cloud_account_id')
        if cloud_account_id:
            self.cloud_account_id = cloud_account_id
        region = kwargs.get('region')
        function_map = {
            'aws_cnr': self.get_aws_architectures,
            'azure_cnr': self.get_azure_architectures,
            'alibaba_cnr': self.get_alibaba_architectures,
        }

        architectures = self.architectures_collection.find({
            'cloud_type': cloud_type, 'flavor': flavor
        })
        for arch in architectures:
            return arch['architecture']
        result = 'Unknown'
        updates = []
        with CachedThreadPoolExecutor(self.mongo_client) as executor:
            func = function_map[cloud_type]
            try:
                arch_future = executor.submit(func, region=region)
                architectures = arch_future.result()
                for item in architectures:
                    item_flavor = item['flavor'].lower()
                    item_architecture = item['architecture']
                    if item_flavor == flavor:
                        result = item_architecture
                    updates.append(UpdateOne(
                        filter={
                            'cloud_type': cloud_type,
                            'flavor': item_flavor
                        },
                        update={'$setOnInsert': {
                            'cloud_type': cloud_type,
                            'flavor': item_flavor,
                            'architecture': item_architecture
                        }},
                        upsert=True,
                    ))
            except Exception as ex:
                LOG.error(ex)
                return result
        if updates:
            self.architectures_collection.bulk_write(updates)
        return result


class ArchitectureAsyncController(BaseAsyncControllerWrapper):
    def _get_controller_class(self):
        return ArchitectureController
