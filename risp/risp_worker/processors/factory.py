from risp.risp_worker.processors.aws import AwsProcessor
from risp.risp_worker.processors.azure import AzureProcessor


class RispProcessors:
    PROCESSORS_MAP = {
        'aws_cnr': AwsProcessor,
        'azure_cnr': AzureProcessor,
    }

    @staticmethod
    def get_processor(cloud_type):
        if cloud_type in RispProcessors.PROCESSORS_MAP:
            return RispProcessors.PROCESSORS_MAP[cloud_type]
        raise ValueError(f'Cloud type {cloud_type} not supported')
