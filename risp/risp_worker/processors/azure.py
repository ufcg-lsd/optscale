import json
from collections import defaultdict
from datetime import datetime, time, timezone, timedelta
import logging
from tools.cloud_adapter.cloud import Cloud as CloudAdapter
from risp.risp_worker.processors.base import RispProcessorBase

LOG = logging.getLogger(__name__)
CHUNK_SIZE = 200


class AzureProcessor(RispProcessorBase):

    @staticmethod
    def _parse_reservation_ids(cloud_resource_id):
        # get order id and reservation id from a string like:
        #   /.../reservationorders/order_id/reservations/reservation_id
        part = cloud_resource_id.split('reservationorders/')[-1]
        parts = part.split('/')
        order_id = parts[0]
        reservation_id = parts[-1]
        return order_id, reservation_id

    def generate_ri_sp_usage(self, cloud_account_id, start_date, end_date):
        # only RI usage supported
        LOG.info(f'Generating RI usage for cloud account {cloud_account_id}')
        ch_expenses_list = []
        ri_resources = self.mongo_client.restapi.resources.find(
            {'cloud_account_id': cloud_account_id,
             'resource_type': 'Reserved Instances'}
        )
        if not ri_resources:
            LOG.info('No reservations found for cloud account %s',
                     cloud_account_id)
            return
        new_expenses_map = defaultdict(lambda: defaultdict(
            lambda: defaultdict(dict)))
        instances = {x['cloud_resource_id']: x.get('region')
                     for x in self.mongo_client.restapi.resources.find(
                        {'cloud_account_id': cloud_account_id,
                         'resource_type': 'Instance'},
                        {'region': 1, 'cloud_resource_id': 1}
                    )}
        _, cloud_account = self.rest_cl.cloud_account_get(cloud_account_id)
        _, organization = self.rest_cl.organization_get(
            cloud_account['organization_id'])
        cloud_account.update(cloud_account['config'])
        azure = CloudAdapter.get_adapter(cloud_account)
        start_date_dt = start_date.date() - timedelta(days=31)
        end_date_dt = end_date.date() + timedelta(days=31)
        offer_exp_cost_per_day = defaultdict(lambda: defaultdict(float))
        region_flavor_price_map = {}
        for reservation in ri_resources:
            offer_id = reservation['cloud_resource_id']
            LOG.info("Start processing reservation %s", offer_id)
            order_id, reservation_id = self._parse_reservation_ids(offer_id)
            try:
                order = azure.reservations.reservation_order.get(
                    order_id, expand="schedule")
            except Exception as e:
                LOG.warning('Failed to get reservation order %s: %s',
                            offer_id, str(e))
                continue
            # list of tuples (payment day, cost)
            cost_plan = list()
            for data in order.plan_information.transactions:
                if start_date_dt <= data.due_date <= end_date_dt:
                    cost_plan.append((
                        datetime.combine(data.due_date, time.min,
                                         tzinfo=timezone.utc),
                        data.pricing_currency_total.amount))
            for i in range(0, len(cost_plan) - 1):
                # calculate expected costs per day as
                #   (monthly cost / number of days)
                days = (cost_plan[i + 1][0] - cost_plan[i][0]).days
                cost = cost_plan[i][1] / days if days else 0
                for j in range(days + 1):
                    offer_exp_cost_per_day[offer_id][
                        cost_plan[i][0] + timedelta(days=j)] = cost
            location_map = {v: k for k, v in azure.location_map.items()}
            start = datetime.fromtimestamp(
                reservation['meta']['start']).strftime('%Y-%m-%dT%H:%M:%S.0Z')
            end = datetime.fromtimestamp(
                reservation['meta']['end']).strftime('%Y-%m-%dT%H:%M:%S.0Z')
            filters = (f'properties/UsageDate ge {start} and '
                       f'properties/UsageDate le {end}')
            details = azure.consumption.reservations_details.list_by_reservation_order_and_reservation(
                reservation_order_id=order_id,
                reservation_id=reservation_id,
                filter=filters
            )
            for detail in details:
                region = instances.get(detail.instance_id.lower())
                if not region:
                    # instance from other subscription
                    LOG.warning('Instance %s not found, skipping',
                                detail.instance_id.lower())
                    continue
                location = location_map.get(region)
                usage_datetime = datetime.combine(detail.usage_date, time.min,
                                                  tzinfo=timezone.utc)
                expected_cost = offer_exp_cost_per_day[offer_id][
                    usage_datetime]
                on_demand_cost = region_flavor_price_map.get(
                    (location, detail.sku_name))
                if not on_demand_cost:
                    _, response = self.insider_cl.get_flavor_prices(
                        'azure', detail.sku_name, location, 'linux',
                        preinstalled=None, quantity=None, billing_method=None,
                        currency=organization['currency']
                    )
                    # price per 1 hour
                    if len(response['prices']) == 0:
                        continue
                    on_demand_cost = response['prices'][0]['price']
                    region_flavor_price_map[
                        (location, detail.sku_name)] = on_demand_cost
                cost = on_demand_cost * detail.used_hours
                offer_cost = expected_cost * detail.used_hours / detail.reserved_hours
                value = new_expenses_map.get(
                    detail.instance_id.lower(), {}).get(usage_datetime, {}).get(
                        offer_id, {}).get(detail.sku_name)
                if value:
                    value = (offer_cost + value[0], cost + value[1],
                             detail.used_hours + value[2],
                             float(detail.instance_flexibility_ratio), 0)
                else:
                    value = (offer_cost, cost, detail.used_hours,
                             float(detail.instance_flexibility_ratio), 0)
                new_expenses_map[detail.instance_id.lower()][usage_datetime][
                    offer_id][detail.sku_name] = value
        cloud_resource_ids = list(new_expenses_map)
        self.save_risp_expenses_to_ch(cloud_resource_ids, new_expenses_map,
                                      offer_exp_cost_per_day, cloud_account_id,
                                      'ri', start_date, end_date)
        self.fill_ri_sp_usage_empty(offer_exp_cost_per_day, cloud_account_id,
                                    start_date, end_date, 'ri')

    def generate_uncovered_usage(self, cloud_account_id, start_date, end_date):
        LOG.info('Start generating uncovered usage for cloud account %s',
                 cloud_account_id)
        raw_expenses = self.mongo_client.restapi.raw_expenses.find({
            'cloud_account_id': cloud_account_id,
            'box_usage': True,
            'meter_details.meter_sub_category': {'$ne': 'Reservation-Base VM'},
            'start_date': {'$gte': start_date},
            'end_date': {'$lte': end_date},
        })
        new_expenses_map = defaultdict(lambda: defaultdict(
            lambda: defaultdict(lambda: (0, 0))))
        for expense in raw_expenses:
            cost = expense['cost']
            usage_hrs = float(expense['usage_quantity'])
            os_type = 'windows' if 'windows' in expense['meter_details'][
                'meter_sub_category'] else 'linux'
            instance_type = json.loads(
                expense.get('additional_properties') or '{}').get(
                    'ServiceType', '') or expense.get('product').split(
                        ', ')[1]
            location = expense.get('resource_location', '')
            res_data = (os_type, instance_type, location)
            total_cost = new_expenses_map[expense['resource_id']][
                expense['start_date']][res_data][0]
            total_usage = new_expenses_map[expense['resource_id']][
                expense['start_date']][res_data][1]
            new_expenses_map[expense['resource_id']][expense['start_date']][
                res_data] = (total_cost + cost, total_usage + usage_hrs)
        self.save_uncovered_expenses_to_ch(new_expenses_map, cloud_account_id,
                                           start_date, end_date)
