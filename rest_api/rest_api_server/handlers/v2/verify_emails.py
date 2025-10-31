from rest_api.rest_api_server.handlers.v2.restore_passwords import (
    RestorePasswordAsyncCollectionHandler)
from rest_api.rest_api_server.controllers.verify_email import (
    VerifyEmailAsyncController)


class VerifyEmailAsyncCollectionHandler(RestorePasswordAsyncCollectionHandler):

    def _get_controller_class(self):
        return VerifyEmailAsyncController

    async def post(self):
        """
        ---
        description: Initialize email verification flow
        tags: [verify_email]
        summary: Initialize email verification flow
        parameters:
        -   in: body
            name: body
            description: email verification parameters
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
        await super().post()
