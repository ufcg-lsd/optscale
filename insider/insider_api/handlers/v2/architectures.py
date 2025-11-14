import json
import logging

from tools.optscale_exceptions.common_exc import (
    WrongArgumentsException, UnauthorizedException, NotFoundException)
from tools.optscale_exceptions.http_exc import OptHTTPError

from insider.insider_api.controllers.architecture import (
    ArchitectureAsyncController)
from insider.insider_api.handlers.v2.base import SecretHandler
from insider.insider_api.utils import ModelEncoder
from insider.insider_api.exceptions import Err

SUPPORTED_CLOUD_TYPES = ['alibaba_cnr', 'azure_cnr', 'aws_cnr']
LOG = logging.getLogger(__name__)


class ArchitectureCollectionHandler(SecretHandler):
    def _get_controller_class(self):
        return ArchitectureAsyncController

    def get_url_params(self):
        return {
            'flavor': self.get_arg('flavor', str),
            'region': self.get_arg('region', str),
            'cloud_account_id': self.get_arg('cloud_account_id', str)
        }

    @staticmethod
    def validate_parameters(cloud_type, params):
        if cloud_type not in SUPPORTED_CLOUD_TYPES:
            raise OptHTTPError(400, Err.OI0010, [cloud_type])
        required_params = [('flavor', str)]
        optional_params = [('region', str), ('cloud_account_id', str)]
        missing_required = [
            p for p, _ in required_params if params.get(p) is None
        ]
        if missing_required:
            message = ', '.join(missing_required)
            raise OptHTTPError(400, Err.OI0011, [message])
        all_params = required_params + optional_params
        region = params.get('region')
        if cloud_type != 'azure_cnr' and not region:
            raise OptHTTPError(400, Err.OI0024, ['region', cloud_type])
        for param, param_type in all_params:
            value = params.get(param)
            if value is not None and not isinstance(value, param_type):
                raise OptHTTPError(400, Err.OI0008, [param])

    async def get(self, cloud_type):
        """
        ---
        tags: [architectures]
        summary: Get architecture for flavor
        description: |
            Get architecture for flavor
            Required permission: cluster secret
        parameters:
        -   in: path
            name: cloud_type
            description: cloud type
            required: true
            type: string
            enum: ['aws_cnr', 'azure_cnr', 'alibaba_cnr']
        -   in: query
            name: flavor
            description: flavor name
            required: true
            type: string
        -   in: query
            name: region
            description: flavor region (required for 'aws_cnr', 'alibaba_cnr')
            required: false
            type: string
        -   in: query
            name: cloud_account_id
            description: cloud account id
            required: false
            type: string
        responses:
            200:
                description: flavor architecture
                schema:
                    type: object
                    properties:
                        cloud_type: {type: string,
                            description: "cloud type"}
                        region: {type: string,
                            description: "region name"}
                        flavor: {type: string,
                            description: "flavor name"}
                        architecture: {type: string,
                            description: "flavor architecture"}
            400:
                description: |
                    Wrong arguments:
                    - OI0008: Invalid argument
                    - OI0010: Cloud is not supported
                    - OI0011: Required argument is not provided
            401:
                description: |
                    Unauthorized:
                    - OI0007: This resource requires authorization
            403:
                description: |
                    Forbidden:
                    - OI0005: Bad secret
        security:
        - secret: []
        """
        self.check_cluster_secret()
        url_params = self.get_url_params()
        self.validate_parameters(cloud_type, url_params)
        try:
            res = await self.controller.get(
                cloud_type=cloud_type, **url_params)
        except WrongArgumentsException as ex:
            raise OptHTTPError.from_opt_exception(400, ex)
        except UnauthorizedException as ex:
            raise OptHTTPError.from_opt_exception(401, ex)
        except NotFoundException as ex:
            raise OptHTTPError.from_opt_exception(404, ex)
        self.set_status(200)
        url_params.pop('cloud_account_id', None)
        self.write(json.dumps({
            'architecture': res, 'cloud_type': cloud_type, **url_params
        }, cls=ModelEncoder))
