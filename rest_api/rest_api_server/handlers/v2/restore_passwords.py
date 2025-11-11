import json
from tools.optscale_exceptions.http_exc import OptHTTPError
from rest_api.rest_api_server.exceptions import Err
from rest_api.rest_api_server.handlers.v1.base_async import (
    BaseAsyncCollectionHandler)
from rest_api.rest_api_server.controllers.restore_password import (
    RestorePasswordAsyncController)
from tools.optscale_exceptions.common_exc import WrongArgumentsException
from rest_api.rest_api_server.utils import (
    check_dict_attribute, check_string_attribute, is_email_format)
from rest_api.rest_api_server.utils import run_task


class RestorePasswordAsyncCollectionHandler(BaseAsyncCollectionHandler):

    def _get_controller_class(self):
        return RestorePasswordAsyncController

    def _validate_params(self, **kwargs):
        expected_params = ['email', 'link_params']
        unexpected = list(
            filter(lambda x: x not in expected_params, kwargs.keys()))
        if unexpected:
            message = ', '.join(unexpected)
            raise OptHTTPError(400, Err.OE0212, [message])
        try:
            email = kwargs.get('email')
            check_string_attribute('email', email)
            if not is_email_format(email):
                raise WrongArgumentsException(Err.OE0218, ['Email', email])
            link_params = kwargs.get('link_params')
            check_dict_attribute('link_params', link_params, allow_empty=True)
        except WrongArgumentsException as ex:
            raise OptHTTPError.from_opt_exception(400, ex)
        super()._validate_params(**kwargs)

    async def post(self):
        """
        ---
        description: Initialize password restore flow
        tags: [restore_password]
        summary: Initialize password restore flow
        parameters:
        -   in: body
            name: body
            description: restore password parameters
            required: true
            schema:
                type: object
                properties:
                    link_params:
                        type: object
                        description: Query parameters added to link
                        required: false
                        example:
                            capability: mlops
        responses:
            201:
                description: Flow initialized and email sent
                schema:
                    type: object
                    example:
                        status: ok
            400:
                description: |
                    Wrong arguments:
                    - OE0212: Unexpected parameters
                    - OE0214: Argument should be a string
                    - OE0215: Wrong argument's length
                    - OE0216: Argument is not provided
                    - OE0218: Argument has incorrect format
                    - OE0344: Argument should be a dictionary
                    - OE0416: Argument should not contain only whitespaces
        """
        data = self._request_body()
        self._validate_params(**data)
        email = data['email']
        await run_task(self.controller.restore_password, email=email,
                       link_params=data.get('link_params', {}))
        self.set_status(201)
        self.write(json.dumps({'status': 'ok'}))
