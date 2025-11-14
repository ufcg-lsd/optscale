from collections import defaultdict
from datetime import datetime, timezone, timedelta

import re
import logging
from risp.risp_worker.processors.base import RispProcessorBase

LOG = logging.getLogger(__name__)
CHUNK_SIZE = 200
HRS_IN_DAY = 24
SECONDS_IN_HOUR = 3600
SECONDS_IN_DAY = 86400


class AwsProcessor(RispProcessorBase):

    @staticmethod
    def _datetime_from_value(value):
        dt_format = '%Y-%m-%dT%H:%M:%SZ'
        if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", value):
            dt_format = '%Y-%m-%dT%H:%M:%S.%fZ'
        return datetime.strptime(value, dt_format).replace(tzinfo=timezone.utc)

    @staticmethod
    def get_expenses_pipeline(offer_type, cloud_account_id, start_date,
                              end_date):
        offer_type_line_item_filter_map = {
            'ri': 'DiscountedUsage',
            'sp': 'SavingsPlanCoveredUsage'
        }
        offer_type_id_field_map = {
            'ri': '$reservation/ReservationARN',
            'sp': '$savingsPlan/SavingsPlanARN'
        }
        offer_type_offer_cost_map = {
            'ri': '$reservation/EffectiveCost',
            'sp': '$savingsPlan/SavingsPlanEffectiveCost'
        }
        if offer_type not in offer_type_id_field_map:
            raise Exception(f'Unknown offer type: {offer_type}')

        return [
            {
                '$match': {
                    'cloud_account_id': cloud_account_id,
                    'start_date': {'$gte': start_date, '$lte': end_date},
                    'box_usage': True,
                    'lineItem/LineItemType': offer_type_line_item_filter_map[
                        offer_type],
                }
            },
            {
                '$group': {
                    '_id': {
                        'start_date': {
                            'month': {'$month': "$start_date"},
                            'day': {'$dayOfMonth': "$start_date"},
                            'year': {'$year': "$start_date"},
                        },
                        'end_date': {
                            'month': {'$month': "$end_date"},
                            'day': {'$dayOfMonth': "$end_date"},
                            'year': {'$year': "$end_date"},
                        },
                        'cloud_resource_id': '$lineItem/ResourceId',
                        'cloud_offer_id': offer_type_id_field_map[offer_type],
                        'instance_type': '$product/instanceType',
                        'description': '$lineItem/LineItemDescription'
                    },
                    'usage_hours': {'$push': {
                        '$cond': [{'$eq': ['$pricing/unit', 'Second']},
                                  0, '$lineItem/UsageAmount']}},
                    'usage_seconds': {'$push': {
                        '$cond': [{'$eq': ['$pricing/unit', 'Second']},
                                  '$lineItem/UsageAmount', 0]}},
                    'on_demand_cost': {'$push': '$pricing/publicOnDemandCost'},
                    'offer_cost': {
                        '$push': offer_type_offer_cost_map[offer_type]
                    },
                    'ri_norm_factor': {
                        '$first': '$lineItem/NormalizationFactor'
                    },
                    'sp_rate': {
                        '$first': '$savingsPlan/SavingsPlanRate'
                    }
                }
            }]

    def get_offers_expenses_by_type(self, offer_type, cloud_account_id,
                                    start_date, end_date):
        pipeline = self.get_expenses_pipeline(offer_type, cloud_account_id,
                                              start_date, end_date)
        return self.mongo_client.restapi.raw_expenses.aggregate(
            pipeline, allowDiskUse=True)

    def process_ri_sp_expenses(self, offer_type, cloud_account_id, start_date,
                               end_date):
        cloud_resource_ids = set()
        new_expenses_map = defaultdict(lambda: defaultdict(
            lambda: defaultdict(dict)))
        offer_expenses = self.get_offers_expenses_by_type(
            offer_type, cloud_account_id, start_date, end_date)
        if offer_type == 'ri':
            # lineItem/NormalizationFactor is missing for RDS instances,
            # use 1 as default value
            default_ri_norm_factor = 1
        else:
            # SP not use lineItem/NormalizationFactor
            default_ri_norm_factor = 0
        for expense in offer_expenses:
            LOG.info('Processing expense: %s', expense)
            expense['offer_type'] = offer_type
            expense['cloud_account_id'] = cloud_account_id
            cloud_resource_id = expense['_id']['cloud_resource_id']
            cloud_offer_id = expense['_id']['cloud_offer_id']
            # remove prefixes if exists
            cloud_resource_id = cloud_resource_id[
                                    cloud_resource_id.find('/') + 1:]
            cloud_offer_id = cloud_offer_id[cloud_offer_id.find('/') + 1:]
            cloud_resource_ids.add(cloud_resource_id)
            exp_start = datetime(**expense['_id']['start_date'],
                                 tzinfo=timezone.utc)
            offer_cost = sum(float(x) for x in expense['offer_cost'])
            on_demand_cost = sum(float(x) for x in expense['on_demand_cost'])
            usage = sum(float(x) for x in expense['usage_hours']) + sum(
                float(x) / SECONDS_IN_HOUR for x in expense['usage_seconds'])
            ri_norm_factor = float(
                expense.get('ri_norm_factor') or default_ri_norm_factor)
            sp_rate = float(expense.get('sp_rate') or 0)
            instance_type = expense['_id'].get(
                'instance_type') or expense['_id'].get('description')
            new_expenses_map[cloud_resource_id][exp_start][cloud_offer_id][
                instance_type] = (offer_cost, on_demand_cost, usage,
                                  ri_norm_factor, sp_rate)
        return new_expenses_map, cloud_resource_ids

    @staticmethod
    def dates_range(start_date, end_date):
        dates = []
        date = start_date.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        while date <= end_date:
            dates.append(date)
            date += timedelta(days=1)
        return dates

    def _sp_expected_cost_per_day(
            self, cloud_account_id, start_date, end_date):
        return self.mongo_client.restapi.raw_expenses.find({
                    'cloud_account_id': cloud_account_id,
                    'start_date': {'$gte': start_date, '$lte': end_date},
                    'lineItem/LineItemType': 'SavingsPlanRecurringFee',
                    'lineItem/UsageStartDate': {'$exists': True}
                }, {'start_date': 1, 'savingsPlan/TotalCommitmentToDate': 1,
                    'resource_id': 1})

    def sp_expected_cost_per_day(self, cloud_account_id, start_date, end_date):
        sp_date_expected_cost = defaultdict(lambda: defaultdict(float))
        expenses = self._sp_expected_cost_per_day(cloud_account_id, start_date,
                                                  end_date)
        for expense in expenses:
            date = expense['start_date'].replace(tzinfo=timezone.utc)
            sp_date_expected_cost[expense['resource_id']][date] = float(
                expense['savingsPlan/TotalCommitmentToDate'])
        return sp_date_expected_cost

    def _ri_expected_cost_per_day(
            self, cloud_account_id, start_date, end_date):
        # RIFee may be created at start of the month
        start_of_month = start_date.replace(day=1, hour=0, minute=0, second=0,
                                            microsecond=0)
        return self.mongo_client.restapi.raw_expenses.find(
            {
                'cloud_account_id': cloud_account_id,
                'start_date': {'$gte': start_of_month, '$lte': end_date},
                'lineItem/LineItemType': 'RIFee',
                'lineItem/UsageStartDate': {'$exists': True}
            },
            {
                'start_date': 1,
                'end_date': 1,
                'reservation/TotalReservedNormalizedUnits': 1,
                'reservation/TotalReservedUnits': 1,
                'reservation/AmortizedUpfrontFeeForBillingPeriod': 1,
                'lineItem/NormalizationFactor': 1,
                'lineItem/UnblendedCost': 1,
                'lineItem/UsageStartDate': 1,
                'resource_id': 1
            })

    def ri_expected_cost_per_day(self, cloud_account_id, start_date, end_date):
        ri_date_expected_cost = defaultdict(lambda: defaultdict(float))
        expenses = self._ri_expected_cost_per_day(
            cloud_account_id, start_date, end_date)
        for expense in expenses:
            # lineItem/TotalReservedNormalizedUnits is missing for RDS instances
            total_norm_hours = float(expense.get(
                'reservation/TotalReservedNormalizedUnits') or expense.get(
                'reservation/TotalReservedUnits'))
            total_cost_per_month = float(
                expense.get('lineItem/UnblendedCost', 0)) + float(expense.get(
                    'reservation/AmortizedUpfrontFeeForBillingPeriod', 0))
            cost_per_n_hr = total_cost_per_month / total_norm_hours
            norm_factor = float(expense.get('lineItem/NormalizationFactor', 1))
            exp_start_date = expense['start_date'].replace(tzinfo=timezone.utc)
            exp_end_date = expense['end_date'].replace(tzinfo=timezone.utc)
            dates = self.dates_range(exp_start_date, exp_end_date)
            for date in dates:
                ri_date_expected_cost[expense['resource_id']][
                    date] = HRS_IN_DAY * norm_factor * cost_per_n_hr
            # the first RIFee expense not includes hours from start of the
            # month to RI purchasing time
            period_start = self._datetime_from_value(
                expense['lineItem/UsageStartDate'])
            if period_start > exp_start_date:
                not_used_hrs = (period_start - exp_start_date
                                ).total_seconds() / SECONDS_IN_HOUR
                ri_date_expected_cost[expense['resource_id']][
                    exp_start_date] = (HRS_IN_DAY - not_used_hrs
                                       ) * norm_factor * cost_per_n_hr
        return ri_date_expected_cost

    def _generate_ri_sp_usage(self, offer_type, cloud_account_id, start_date,
                              end_date):
        LOG.info('Generating expenses for offer type: %s', offer_type)
        expected_values = {
            'ri': self.ri_expected_cost_per_day,
            'sp': self.sp_expected_cost_per_day,
        }
        func = expected_values[offer_type]
        offer_exp_cost_per_day = func(cloud_account_id, start_date, end_date)
        (new_expenses_map, cloud_resource_ids) = self.process_ri_sp_expenses(
            offer_type, cloud_account_id, start_date, end_date)
        cloud_resource_ids = list(cloud_resource_ids)
        self.save_risp_expenses_to_ch(cloud_resource_ids, new_expenses_map,
                                      offer_exp_cost_per_day, cloud_account_id,
                                      offer_type, start_date, end_date)
        self.fill_ri_sp_usage_empty(
            offer_exp_cost_per_day, cloud_account_id, start_date, end_date,
            offer_type)

    def generate_ri_sp_usage(self, cloud_account_id, start_date, end_date):
        for offer_type in ['ri', 'sp']:
            self._generate_ri_sp_usage(offer_type, cloud_account_id,
                                       start_date, end_date)

    def get_uncovered_raw_expenses(self, cloud_account_id, start_date,
                                   end_date):
        return self.mongo_client.restapi.raw_expenses.find({
            'cloud_account_id': cloud_account_id,
            'start_date': {'$gte': start_date, '$lte': end_date},
            'box_usage': True,
            'lineItem/LineItemType': 'Usage'},
            {
                'start_date': 1,
                'resource_id': 1,
                'pricing/unit': 1,
                'lineItem/UsageAmount': 1,
                'lineItem/UnblendedCost': 1,
                'pricing/publicOnDemandCost': 1,
                'product/operatingSystem': 1,
                'product/instanceType': 1,
                'product/usagetype': 1,
                'product/region': 1,
                'lineItem/AvailabilityZone': 1
            }
        )

    def generate_uncovered_usage(self, cloud_account_id, start_date, end_date):
        LOG.info('Start generating uncovered usage for cloud account %s',
                 cloud_account_id)
        new_expenses_map = defaultdict(lambda: defaultdict(
            lambda: defaultdict(lambda: (0, 0))))
        raw_expenses = self.get_uncovered_raw_expenses(
            cloud_account_id, start_date, end_date)
        for expense in raw_expenses:
            # pricing/publicOnDemandCost may be missing for Fargate expenses and
            # lineItem/UnblendedCost may be missing for Lambda
            cost = expense.get('pricing/publicOnDemandCost') or expense.get(
                'lineItem/UnblendedCost')
            if 'SpotUsage-Fargate' in expense.get('product/usagetype', ''):
                # spot Fargate tasks can't be covered by RI/SP
                continue
            if cost is None:
                if 'metal' in expense.get('product/instanceType', ''):
                    # skip instances on dedicated hosts
                    continue
                if 'lineItem/UsageAmount' not in expense:
                    continue
                raise Exception('Unsupported expense for resource %s, '
                                'cloud account: %s, date: %s' % (
                                    expense['resource_id'],
                                    cloud_account_id,
                                    expense['start_date']))
            cost = float(cost)
            usage_hrs = float(expense['lineItem/UsageAmount'])
            if 'second' in expense['pricing/unit'].lower():
                usage_hrs = usage_hrs / SECONDS_IN_HOUR
            os_type = expense.get('product/operatingSystem', '')
            instance_type = expense.get('product/instanceType', '')
            location = expense.get('lineItem/AvailabilityZone') or expense.get(
                'product/region', '')
            res_data = (os_type, instance_type, location)
            total_cost = new_expenses_map[expense['resource_id']][
                expense['start_date']][res_data][0]
            total_usage = new_expenses_map[expense['resource_id']][
                expense['start_date']][res_data][1]
            new_expenses_map[expense['resource_id']][expense['start_date']][
                res_data] = (total_cost + cost, total_usage + usage_hrs)
        self.save_uncovered_expenses_to_ch(new_expenses_map, cloud_account_id,
                                           start_date, end_date)
