from requests import HTTPError
from requests.models import Response
from unittest.mock import patch, ANY
from rest_api.rest_api_server.tests.unittests.test_api_base import TestApiBase


class TestRestorePassword(TestApiBase):
    def setUp(self, version='v2'):
        patch('optscale_client.config_client.client.Client.cluster_secret'
              ).start()
        patch('optscale_client.config_client.client.Client.auth_url').start()
        patch('optscale_client.config_client.client.Client.herald_url').start()
        super().setUp(version)

    def test_restore_password_no_link_params(self):
        email = 'example@email.com'
        p_auth = patch('optscale_client.auth_client.client_v2.Client'
                       '.verification_code_create',
                       return_value=(201, {'email': email})).start()
        p_herald = patch('optscale_client.herald_client.client_v2.Client'
                         '.email_send').start()
        code, resp = self.client.restore_password(email)
        self.assertEqual(code, 201)
        self.assertEqual(resp['status'], 'ok')
        p_auth.assert_called_once_with(email, ANY)
        p_herald.assert_called_once_with(
            [email], 'OptScale password recovery',
            template_type='restore_password',
            template_params={
                'texts': {'code': ANY},
                'links': {'restore_button': ANY}}
        )

    def test_restore_password_link_params(self):
        email = 'example@email.com'
        p_auth = patch('optscale_client.auth_client.client_v2.Client'
                       '.verification_code_create',
                       return_value=(201, {'email': email})).start()
        p_herald = patch('optscale_client.herald_client.client_v2.Client'
                         '.email_send').start()
        code, resp = self.client.restore_password(
            email, link_params={'mode': 'mlops'})
        self.assertEqual(code, 201)
        self.assertEqual(resp['status'], 'ok')
        p_auth.assert_called_once_with(email, ANY)
        link = p_herald.call_args[1]['template_params']['links'][
            'restore_button']
        self.assertIn('mode=mlops', link)

    def test_invalid_email(self):
        for body in [{'email': None}, {}]:
            code, response = self.client.post('restore_password', body)
            self.assertEqual(code, 400)
            self.verify_error_code(response, 'OE0216')
        for email in ['', ''.join('x' for _ in range(0, 256))]:
            code, response = self.client.post(
                'restore_password', {'email': email})
            self.assertEqual(code, 400)
            self.verify_error_code(response, 'OE0215')
        for email, expected_error_code in {
            'invalid@format': 'OE0218',
            ' ': 'OE0416',
            123: 'OE0214'
        }.items():
            code, response = self.client.post(
                'restore_password', {'email': email})
            self.assertEqual(code, 400)
            self.verify_error_code(response, expected_error_code)

    def test_unexpected_parameters(self):
        code, response = self.client.post('restore_password', {
            'email': 'example@email.com',
            'link_params': {'test': 1},
            'another': 'parameter'
        })
        self.assertEqual(code, 400)
        self.verify_error_code(response, 'OE0212')

    def test_link_params(self):
        email = 'example@email.com'
        for value in [1, 'test', ['test']]:
            code, resp = self.client.restore_password(email, link_params=value)
            self.assertEqual(code, 400)
            self.assertEqual(resp['error']['error_code'], 'OE0344')

    def test_method_not_allowed(self):
        for method in ['get', 'patch', 'delete', 'put']:
            func = getattr(self.client, method)
            code, response = func('restore_password', {})
            self.assertEqual(code, 405)
            self.verify_error_code(response, 'OE0245')
            self.assertEqual(response['error']['params'], [method.upper()])

    def test_auth_error(self):
        def raise_404(*_args, **_kwargs):
            err = HTTPError('Email not found')
            err.response = Response()
            err.response.status_code = 409
            raise err

        email = 'example@email.com'
        p_auth = patch('optscale_client.auth_client.client_v2.Client'
                       '.verification_code_create',
                       side_effect=raise_404).start()
        p_herald = patch('optscale_client.herald_client.client_v2.Client'
                         '.email_send').start()
        code, resp = self.client.restore_password(email)
        self.assertEqual(code, 201)
        self.assertEqual(resp['status'], 'ok')
        p_auth.assert_called_once_with(email, ANY)
        p_herald.assert_not_called()
