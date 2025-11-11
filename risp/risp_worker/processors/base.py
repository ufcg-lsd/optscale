import clickhouse_connect
import logging
from collections import defaultdict
from datetime import timezone
from pymongo import MongoClient
from optscale_client.insider_client.client import Client as InsiderClient
from optscale_client.rest_api_client.client_v2 import Client as RestClient

CH_DB_NAME = 'risp'
CHUNK_SIZE = 200
LOG = logging.getLogger(__name__)


class RispProcessorBase:
    def __init__(self, config_client):
        self.config_client = config_client
        self._mongo_client = None
        self._clickhouse_client = None
        self._insider_cl = None
        self._rest_cl = None

    @property
    def clickhouse_client(self):
        if self._clickhouse_client is None:
            user, password, host, _, port, secure = (
                self.config_client.clickhouse_params())
            self._clickhouse_client = clickhouse_connect.get_client(
                host=host, password=password, database=CH_DB_NAME, user=user,
                port=port, secure=secure)
        return self._clickhouse_client

    @property
    def insider_cl(self):
        if self._insider_cl is None:
            self._insider_cl = InsiderClient(
                url=self.config_client.insider_url(),
                secret=self.config_client.cluster_secret())
        return self._insider_cl

    @property
    def mongo_client(self):
        if self._mongo_client is None:
            mongo_params = self.config_client.mongo_params()
            self._mongo_client = MongoClient(mongo_params[0])
        return self._mongo_client

    @property
    def rest_cl(self):
        if self._rest_cl is None:
            self._rest_cl = RestClient(
                url=self.config_client.restapi_url(),
                secret=self.config_client.cluster_secret(),
                verify=False)
        return self._rest_cl

    def get_ri_sp_usage_expenses(self, cloud_account_id, resource_ids,
                                 offer_type, start_date, end_date):
        return self.clickhouse_client.query(
            """SELECT resource_id, date, instance_type, offer_id,
                    any(ri_norm_factor), any(sp_rate),
                    any(expected_cost), sum(offer_cost * sign),
                    sum(on_demand_cost * sign), sum(usage * sign)
                FROM ri_sp_usage
                WHERE cloud_account_id = %(cloud_account_id)s
                    AND offer_type = %(offer_type)s
                    AND date >= %(start_date)s
                    AND date <= %(end_date)s
                    AND resource_id in %(resource_ids)s
                GROUP BY resource_id, date, instance_type, offer_id
                HAVING sum(sign) > 0""",
            parameters={
                'cloud_account_id': cloud_account_id,
                'start_date': start_date,
                'end_date': end_date,
                'offer_type': offer_type,
                'resource_ids': resource_ids
            }).result_rows

    def get_uncovered_usage_expenses(self, cloud_account_id, resource_ids,
                                     start_date, end_date):
        return self.clickhouse_client.query(
            """SELECT instance_type, os, location, resource_id, date,
                    sum(cost * sign), sum(usage * sign)
                FROM uncovered_usage
                WHERE cloud_account_id = %(cloud_account_id)s
                    AND date >= %(start_date)s
                    AND date <= %(end_date)s
                    AND resource_id in %(resource_ids)s
                GROUP BY resource_id, date, location, os,
                    instance_type
                HAVING sum(sign) > 0
            """, parameters={
                'cloud_account_id': cloud_account_id,
                'start_date': start_date,
                'end_date': end_date,
                'resource_ids': resource_ids
            }).result_rows

    def insert_clickhouse_expenses(self, expenses, table='ri_sp_usage'):
        column_names = expenses[0].keys()
        insert_data = []
        for exp in expenses:
            d = list(exp.values())
            insert_data.append(d)
        self.clickhouse_client.insert(
            table,
            insert_data,
            column_names=column_names
        )

    def _get_offer_date_map(self, offer_ids, cloud_account_id,
                            start_date, end_date):
        result = defaultdict(list)
        offer_dates_q = self.clickhouse_client.query(
            """SELECT DISTINCT offer_id, date
               FROM ri_sp_usage
               WHERE cloud_account_id = %(cloud_account_id)s AND
                 date >= %(start_date)s AND date <= %(end_date)s AND
                 offer_id in %(offer_ids)s
            """, parameters={
                'cloud_account_id': cloud_account_id,
                'start_date': start_date,
                'end_date': end_date,
                'offer_ids': offer_ids
            })
        for data in offer_dates_q.result_rows:
            result[data[0]].append(data[1])
        return result

    def fill_ri_sp_usage_empty(self, offer_exp_cost_per_day, cloud_account_id,
                               start_date, end_date, offer_type):
        offer_dates_map = self._get_offer_date_map(
            list(offer_exp_cost_per_day), cloud_account_id, start_date,
            end_date)
        ch_expenses = []
        for offer_id, data in offer_exp_cost_per_day.items():
            exist_dates = offer_dates_map.get(offer_id, [])
            for date, cost in data.items():
                if date not in exist_dates:
                    LOG.info('Will add empty expense for offer %s, date: %s',
                             offer_id, date)
                    ch_expenses.append(self.ri_sp_usage_expense(
                        cloud_account_id, '', date, '', offer_id, offer_type,
                        0, 0, 0, 0, 0, cost, sign=1))
        LOG.info('Will add %s empty expense', len(ch_expenses))
        if ch_expenses:
            self.insert_clickhouse_expenses(ch_expenses)

    def save_risp_expenses_to_ch(self, cloud_resource_ids, new_expenses_map,
                                 offer_exp_cost_per_day, cloud_account_id,
                                 offer_type, start_date, end_date):
        ch_expenses_list = []
        for i in range(0, len(cloud_resource_ids), CHUNK_SIZE):
            cloud_resource_ids_chunk = cloud_resource_ids[i:i + CHUNK_SIZE]
            existing_expenses = self.get_ri_sp_usage_expenses(
                cloud_account_id, cloud_resource_ids_chunk, offer_type,
                start_date, end_date)
            for existing_expense in existing_expenses:
                (cloud_resource_id, date, instance_type, offer_cloud_res_id,
                 ri_norm_factor, sp_rate, expected_cost, offer_cost,
                 on_demand_cost, usage) = existing_expense
                date = date.replace(tzinfo=timezone.utc)
                existing_expense_values = (offer_cost, on_demand_cost, usage,
                                           ri_norm_factor, sp_rate)
                new_expense_values = new_expenses_map.get(
                    cloud_resource_id, {}).get(date, {}).get(
                    offer_cloud_res_id, {}).get(instance_type)
                if not new_expense_values:
                    continue
                elif new_expense_values == existing_expense_values:
                    # not update already existing record
                    new_expenses_map[cloud_resource_id][date].pop(
                        offer_cloud_res_id)
                    continue
                # cancel record for existing record
                ch_expenses_list.append(
                    self.ri_sp_usage_expense(
                        cloud_account_id, cloud_resource_id, date,
                        instance_type, offer_cloud_res_id, offer_type,
                        on_demand_cost, offer_cost, usage, ri_norm_factor,
                        sp_rate, expected_cost, sign=-1))

        for cloud_resource_id, data in new_expenses_map.items():
            for date, offer_data in data.items():
                for cloud_offer_id, instance_type_data in offer_data.items():
                    for instance_type, (offer_cost, on_demand_cost, usage,
                                        ri_norm_factor, sp_rate
                                        ) in instance_type_data.items():
                        expected_cost = offer_exp_cost_per_day.get(
                            cloud_offer_id, {}).get(date, 0)
                        ch_expenses_list.append(
                            self.ri_sp_usage_expense(
                                cloud_account_id, cloud_resource_id, date,
                                instance_type, cloud_offer_id, offer_type,
                                on_demand_cost, offer_cost, usage,
                                ri_norm_factor, sp_rate, expected_cost, 1))
        LOG.info('Will add %s expenses to ri_sp_usage', len(ch_expenses_list))
        if ch_expenses_list:
            self.insert_clickhouse_expenses(ch_expenses_list)

    def save_uncovered_expenses_to_ch(self, new_expenses_map, cloud_account_id,
                                      start_date, end_date):
        cloud_resource_ids = list(new_expenses_map)
        ch_expenses_list = []
        for i in range(0, len(cloud_resource_ids), CHUNK_SIZE):
            cloud_resource_ids_chunk = cloud_resource_ids[i:i + CHUNK_SIZE]
            existing_expenses = self.get_uncovered_usage_expenses(
                cloud_account_id, cloud_resource_ids_chunk, start_date,
                end_date)
            for existing_expense in existing_expenses:
                (instance_type, os_type, location, cloud_resource_id, date,
                 cost, usage) = existing_expense
                res_data = (os_type, instance_type, location)
                date = date.replace(tzinfo=timezone.utc)
                existing_expense_values = (cost, usage)
                new_expense_values = new_expenses_map.get(
                    cloud_resource_id, {}).get(date, {}).get(res_data)
                if not new_expense_values:
                    continue
                elif new_expense_values == existing_expense_values:
                    # not update already existing record
                    new_expenses_map[cloud_resource_id].pop(date)
                    continue
                # cancel record for existing record
                ch_expenses_list.append(
                    self.uncovered_usage_expense(
                        instance_type, os_type, location, cloud_account_id,
                        date, cloud_resource_id, usage, cost, sign=-1))

        for cloud_resource_id, data in new_expenses_map.items():
            for date, usage_data in data.items():
                for res_data, cost_data in usage_data.items():
                    (os_type, instance_type, location) = res_data
                    cost, usage = cost_data
                    ch_expenses_list.append(
                        self.uncovered_usage_expense(
                            instance_type, os_type, location, cloud_account_id,
                            date, cloud_resource_id, usage, cost, sign=1))
        LOG.info('Will add %s expenses to uncovered_usage',
                 len(ch_expenses_list))
        if ch_expenses_list:
            self.insert_clickhouse_expenses(ch_expenses_list,
                                            table='uncovered_usage')

    @staticmethod
    def ri_sp_usage_expense(cloud_account_id, resource_id, date, instance_type,
                            offer_id, offer_type, on_demand_cost, offer_cost,
                            usage, ri_norm_factor, sp_rate, expected_cost,
                            sign=1):
        return {
            'cloud_account_id': cloud_account_id,
            'resource_id': resource_id,
            'date': date,
            'instance_type': instance_type,
            'offer_id': offer_id,
            'offer_type': offer_type,
            'on_demand_cost': on_demand_cost,
            'offer_cost': offer_cost,
            'usage': usage,
            'ri_norm_factor': ri_norm_factor,
            'sp_rate': sp_rate,
            'expected_cost': expected_cost,
            'sign': sign
        }

    @staticmethod
    def uncovered_usage_expense(
            instance_type, os_type, location, cloud_account_id, date,
            resource_id, usage, cost, sign=1):
        return {
            'cloud_account_id': cloud_account_id,
            'date': date,
            'resource_id': resource_id,
            'instance_type': instance_type,
            'os': os_type,
            'location': location,
            'cost': cost,
            'usage': usage,
            'sign': sign
        }

    def generate_ri_sp_usage(self, cloud_account_id, start_date, end_date):
        raise NotImplementedError()

    def generate_uncovered_usage(self, cloud_account_id, start_date, end_date):
        raise NotImplementedError()

    def process_task(self, cloud_account_id, start_date, end_date):
        self.generate_ri_sp_usage(cloud_account_id, start_date, end_date)
        self.generate_uncovered_usage(cloud_account_id, start_date, end_date)
