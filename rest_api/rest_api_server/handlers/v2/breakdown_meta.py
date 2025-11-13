from rest_api.rest_api_server.controllers.breakdown_meta import (
    BreakdownMetaAsyncController)
from rest_api.rest_api_server.handlers.v2.expenses import (
    FilteredExpensesBaseAsyncHandler)
from tools.optscale_exceptions.http_exc import OptHTTPError
from rest_api.rest_api_server.exceptions import Err


class BreakdownMetaAsyncHandler(FilteredExpensesBaseAsyncHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.str_filters = ['breakdown_by']

    def _get_controller_class(self):
        return BreakdownMetaAsyncController

    async def get(self, organization_id, **url_params):
        """
        ---
        description: |
            Get breakdown by meta
            Required permission: INFO_ORGANIZATION or CLUSTER_SECRET
        tags: [expenses]
        summary: Get breakdown by meta
        parameters:
        -   name: organization_id
            in: path
            description: Organization id
            required: true
            type: string
        -   name: breakdown_by
            in: query
            description: meta key for breakdown
            required: true
            type: string
        -   name: start_date
            in: query
            description: Start date (timestamp in seconds)
            required: true
            type: integer
        -   name: end_date
            in: query
            description: End date (timestamp in seconds)
            required: true
            type: integer
        -   name: first_seen_gte
            in: query
            description: |
                Timestamp in seconds resource first seen is greater then
            required: false
            type: integer
        -   name: fist_seen_lte
            in: query
            description: |
                Timestamp in seconds resource first seen is less then
            required: false
            type: integer
        -   name: last_seen_gte
            in: query
            description: |
                Timestamp in seconds resource first seen is greater then
            required: false
            type: integer
        -   name: last_seen_lte
            in: query
            description: |
                Timestamp in seconds resource last seen is less then
            required: false
            type: integer
        -   name: cloud_account_id
            in: query
            description: cloud account id
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: pool_id
            in: query
            description: >
                handle pool id (and it's children if pool_id ends with a + sign)
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: owner_id
            in: query
            description: resource owner id
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: region
            in: query
            description: region
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: service_name
            in: query
            description: service_name
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: resource_type
            in: query
            description: >
                resource_type in format resource_type:identity.
                Supported identity values - [regular, cluster, environment]
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: active
            in: query
            description: Active
            required: false
            type: boolean
        -   name: recommendations
            in: query
            description: Recommendations
            required: false
            type: boolean
        -   name: constraint_violated
            in: query
            description: constraint_violated
            required: false
            type: boolean
        -   name: created_by_kind (for kubernetes only)
            in: query
            description: created_by_kind
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: created_by_name (for kubernetes only)
            in: query
            description: created_by_name
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: k8s_namespace (for kubernetes only)
            in: query
            description: k8s_namespace
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: k8s_node (for kubernetes only)
            in: query
            description: k8s_node
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: k8s_service (for kubernetes only)
            in: query
            description: k8s_service
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: tag
            in: query
            description: tag name
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: without_tag
            in: query
            description: tag name
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: name_like
            in: query
            description: name regular expression
            required: false
            type: string
        -   name: cloud_resource_id_like
            in: query
            description: cloud_resource_id regular expression
            required: false
            type: string
        -   name: traffic_from
            in: query
            description: >
                traffic_from filter in <region_name>:<cloud_type> format or 'ANY'
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: traffic_to
            in: query
            description: >
                traffic_to filter in <region_name>:<cloud_type> format or 'ANY'
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        -   name: meta
            in: query
            description: meta field
            required: false
            type: array
            collectionFormat: multi
            items:
                type: string
        responses:
            200:
                description: Breakdown meta data
                schema:
                    type: object
                    properties:
                        start_date:
                            type: integer
                            description: start date (timestamp in seconds)
                            example: 1643673600
                        end_date:
                            type: integer
                            description: end date (timestamp in seconds)
                            example: 1643673600
                        breakdown:
                            type: object
                            description: breakdown by day
                            example:
                                1640995200:
                                    breakdown_by_value_1:
                                        cost: 18.80
                                        count: 2
                                    breakdown_by_value_2:
                                        cost: 10.30
                                        count: 1
                                1641168000:
                                    breakdown_by_value_1:
                                        cost: 8.40
                                        count: 1
                                    breakdown_by_value_2:
                                        cost: 13.30
                                        count: 2
                        totals:
                            type: object
                            description: calculated totals
                            example:
                                breakdown_by_value_1:
                                    cost: 34.80
                                    count: 3
                                breakdown_by_value_2:
                                    cost: 20.88
                                    count: 2
            400:
                description: |
                    Wrong arguments:
                    - OE0217: Invalid query parameter
                    - OE0216: Argument is not provided
                    - OE0223: Argument should be integer
                    - OE0224: Wrong integer value
                    - OE0212: Unexpected parameters
                    - OE0446: "end_date" should be greater than "start_date"
                    - OE0499: Incorrect resource type identity
            401:
                description: |
                    Unauthorized:
                    - OE0235: Unauthorized
                    - OE0237: This resource requires authorization
            403:
                description: |
                    Forbidden:
                    - OE0234: Forbidden
                    - OE0236: Bad secret
            404:
                description: |
                    Not found:
                    - OE0002: Organization not found
            424:
                description: |
                    Failed dependency:
                    - OE0445: Organization doesn't have any cloud accounts connected
        security:
        - token: []
        - secret: []
        """
        await super().get(organization_id, **url_params)

    def get_expense_arguments(self, filter_required=True):
        args = super().get_expense_arguments()
        breakdown_by = self.get_arg('breakdown_by', str)
        if breakdown_by is None:
            raise OptHTTPError(400, Err.OE0216, ['breakdown_by'])
        return args
