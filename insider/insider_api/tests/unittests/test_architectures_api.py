from unittest.mock import patch
from insider.insider_api.tests.unittests.test_api_base import TestBase


class TestArchitecturesApi(TestBase):
    def test_invalid_cloud_type(self):
        code, resp = self.client.get_architecture('invalid_cloud_type', 'test')
        self.assertEqual(code, 400)
        self.verify_error_code(resp, 'OI0010')

    def test_missing_param(self):
        code, resp = self.client.get_architecture('aws_cnr', None)
        self.assertEqual(code, 400)
        self.verify_error_code(resp, 'OI0011')

    def test_missing_region(self):
        for cloud_type in ['aws_cnr', 'alibaba_cnr']:
            code, resp = self.client.get_architecture(cloud_type, True)
            self.assertEqual(code, 400)
            self.verify_error_code(resp, 'OI0024')

        patch(
            'insider.insider_api.controllers.architecture.'
            'ArchitectureController.get_azure_architectures',
            return_value=[]
        ).start()
        code, resp = self.client.get_architecture('azure_cnr', True)
        self.assertEqual(code, 200)

    def test_get_aws_architecture(self):
        patch(
            'insider.insider_api.controllers.architecture.'
            'ArchitectureController._get_aws_flavors',
            return_value=[{
                'InstanceType': 'test_flavor',
                'ProcessorInfo': {
                    'SupportedArchitectures': ['test_architecture']
                },
            }]
        ).start()
        for f, a in {
            'test_flavor': 'test_architecture',
            'unknown_flavor': 'Unknown'
        }.items():
            code, resp = self.client.get_architecture(
                'aws_cnr', f, region='t')
            self.assertEqual(code, 200)
            self.assertEqual(resp, {
                'architecture': a,
                'cloud_type': 'aws_cnr',
                'flavor': f,
                'region': 't'
            })

    def test_get_azure_architecture(self):
        patch(
            'insider.insider_api.controllers.architecture.'
            'ArchitectureController._get_azure_flavors',
            return_value={
                'test_flavor': {
                    'name': 'test_flavor',
                    'architecture': 'test_architecture',
                }
            }
        ).start()
        for f, a in {
            'test_flavor': 'test_architecture',
            'unknown_flavor': 'Unknown'
        }.items():
            code, resp = self.client.get_architecture(
                'azure_cnr', f, region='t')
            self.assertEqual(code, 200)
            self.assertEqual(resp, {
                'architecture': a,
                'cloud_type': 'azure_cnr',
                'flavor': f,
                'region': 't'
            })

    def test_get_alibaba_architecture(self):
        patch(
            'insider.insider_api.controllers.architecture.'
            'ArchitectureController._get_alibaba_flavors',
            return_value={
                'test_flavor': {
                    'CpuArchitecture': 'test_architecture',
                }
            }
        ).start()
        for f, a in {
            'test_flavor': 'test_architecture',
            'unknown_flavor': 'Unknown'
        }.items():
            code, resp = self.client.get_architecture(
                'alibaba_cnr', f, region='t')
            self.assertEqual(code, 200)
            self.assertEqual(resp, {
                'architecture': a,
                'cloud_type': 'alibaba_cnr',
                'flavor': f,
                'region': 't'
            })

    def test_get_cached(self):
        request_mock = patch(
            'insider.insider_api.controllers.architecture.'
            'ArchitectureController._get_aws_flavors',
            return_value=[{
                'InstanceType': 'test_flavor',
                'ProcessorInfo': {
                    'SupportedArchitectures': ['test_architecture']
                },
            }]
        ).start()

        code, resp = self.client.get_architecture(
            'aws_cnr', 'not_exists', region='t')
        self.assertEqual(code, 200)
        self.assertEqual(resp['architecture'], 'Unknown')
        request_mock.assert_called_once_with('t')
        request_mock.reset_mock()

        code, resp = self.client.get_architecture(
            'aws_cnr', 'test_flavor', region='t', cloud_account_id='123')
        self.assertEqual(code, 200)
        self.assertEqual(resp['architecture'], 'test_architecture')
        request_mock.assert_not_called()
