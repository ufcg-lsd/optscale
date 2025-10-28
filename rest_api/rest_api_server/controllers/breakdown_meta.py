import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from rest_api.rest_api_server.controllers.base_async import BaseAsyncControllerWrapper
from rest_api.rest_api_server.controllers.breakdown_expense import BreakdownBaseController
from rest_api.rest_api_server.controllers.expense import NOT_SET_NAME
from tools.optscale_data.clickhouse import ExternalDataConverter

LOG = logging.getLogger(__name__)
DAY_IN_SECONDS = 86400
UNHASHABLE_NAME = '(unhashable)'


class BreakdownMetaController(BreakdownBaseController):
    @staticmethod
    def get_date_points(start_date, end_date, last_point=None):
        current_point = int(datetime.fromtimestamp(start_date).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp())
        points = []
        while current_point <= end_date:
            points.append(current_point)
            current_point += DAY_IN_SECONDS
            if last_point and current_point > last_point:
                break
        return points

    def _aggregate_resource_data(self, match_query, **kwargs):
        breakdown_by = kwargs['breakdown_by']
        key = f'$meta.{breakdown_by}'
        project_stage = {
            '_id': 1,
            'cluster_type_id': 1,
            'breakdown_by': key,
            'first_seen': 1,
            'last_seen': 1
        }

        res = self.resources_collection.aggregate([
            {'$match': match_query},
            {'$project': project_stage},
        ], allowDiskUse=True)
        return res

    def _extract_values_from_data(self, resources_data, breakdown_by):
        def extract_value(value):
            value = NOT_SET_NAME if value is None else value
            if not callable(getattr(type(value), "__hash__", None)):
                value = UNHASHABLE_NAME
            return str(value)

        clusters = set()
        cnt_map = defaultdict(int)
        resources_table = []
        for data in resources_data:
            _id = data['_id']
            cluster_type_id = data.get('cluster_type_id')
            if cluster_type_id:
                clusters.add(_id)
                continue
            breakdown_by_value = extract_value(data.get('breakdown_by'))
            resources_table.append({
                'id': _id,
                'breakdown_by': breakdown_by_value,
                'first_seen': data.get('first_seen'),
                'last_seen': data.get('last_seen')
            })
            cnt_map[breakdown_by_value] += 1
        if clusters and not resources_table:
            sub_resources = self.resources_collection.find(
                {'cluster_id': {'$in': list(clusters)}, 'deleted_at': 0},
                ['meta', 'first_seen', 'last_seen'])
            for s in sub_resources:
                breakdown_by_value = extract_value(
                    s.get('meta', {}).get(breakdown_by))
                resources_table.append(
                    {
                        'id': s['_id'],
                        'breakdown_by': breakdown_by_value,
                        'first_seen': s.get('first_seen'),
                        'last_seen': s.get('last_seen')
                    }
                )
                cnt_map[breakdown_by_value] += 1
        return resources_table, cnt_map

    def get_breakdown_expenses(self, cloud_account_ids, resources):
        expenses = self.execute_clickhouse(
            query=f"""
                SELECT resources.breakdown_by, sum(cost*sign), date
                FROM expenses
                JOIN resources ON expenses.resource_id = resources.id
                WHERE expenses.date >= %(start_date)s
                    AND expenses.date <= %(end_date)s
                    AND cloud_account_id in %(cloud_account_ids)s
                GROUP BY resources.breakdown_by, date
            """,
            parameters={
                'start_date': self.start_date,
                'end_date': self.end_date,
                'cloud_account_ids': list(cloud_account_ids)
            },
            external_data=ExternalDataConverter()([{
                'name': 'resources',
                'structure': [
                    ('id', 'String'),
                    ('breakdown_by', 'Nullable(String)'),
                ],
                'data': [{
                    'id': r['id'],
                    'breakdown_by': r['breakdown_by']
                } for r in resources]
            }]),
        )
        result = defaultdict(dict)
        for e in expenses:
            result[int(e[2].timestamp())][e[0]] = e[1]
        return result

    def process_data(self, resources_data, organization_id, filters, **kwargs):
        def inner_breakdown_factory():
            return defaultdict(int, {'cost': 0, 'count': 0})

        breakdown_by = filters['breakdown_by']
        extracted_values = self._extract_values_from_data(
            resources_data, breakdown_by)
        resources_table, cnt_map = extracted_values
        _, organization_cloud_accs = self.get_organization_and_cloud_accs(
            organization_id)
        cloud_account_ids = list(map(lambda x: x.id, organization_cloud_accs))
        expenses = self.get_breakdown_expenses(
            cloud_account_ids, resources_table)
        points = self.get_date_points(self.start_date, self.end_date)
        breakdown = {p: defaultdict(inner_breakdown_factory) for p in points}
        totals = defaultdict(inner_breakdown_factory)

        # calculate counts for breakdown and totals
        for r in resources_table:
            r_points = self.get_date_points(
                r.get('first_seen'), r.get('last_seen'),
                last_point=self.end_date
            )
            breakdown_by = r['breakdown_by']
            totals[breakdown_by]['count'] += 1
            for p in r_points:
                if p not in breakdown:
                    continue
                breakdown[p][breakdown_by]['count'] += 1

        # calculate costs for breakdown and totals
        for dt, costs in expenses.items():
            if dt in breakdown:
                for key, v in costs.items():
                    if key in breakdown[dt]:
                        breakdown[dt][key]['cost'] = v
                    totals[key]['cost'] += v

        return {
            'breakdown': breakdown,
            'totals': totals,
            'start_date': self.start_date,
            'end_date': self.end_date,
        }


class BreakdownMetaAsyncController(BaseAsyncControllerWrapper):
    def _get_controller_class(self):
        return BreakdownMetaController
