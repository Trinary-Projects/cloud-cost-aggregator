"""
GCP BigQuery Billing Export collector
"""
from datetime import date, timedelta
from typing import List
from decimal import Decimal
import os

from google.cloud import bigquery
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPIError

from collectors.base_collector import BaseCollector, CostRecord
from config import GCPConfig


class GCPCollector(BaseCollector):
    """
    Collector for GCP costs using BigQuery billing export

    Requires:
    1. Billing export enabled in GCP Console
    2. BigQuery dataset with billing data
    """

    def __init__(self, config: GCPConfig):
        """
        Initialize GCP collector

        Args:
            config: GCP configuration
        """
        super().__init__('gcp')
        self.config = config
        self.client = None
        self._initialize_client()

    @property
    def _billing_export_sources(self) -> List[dict]:
        """Return billing export table metadata for each configured account."""
        sources = []
        for billing_account_id in self.config.billing_account_ids:
            project_id, dataset = self.config.billing_export_location_map.get(
                billing_account_id,
                (self.config.billing_export_project_id, self.config.bigquery_dataset)
            )
            sources.append({
                'billing_account_id': billing_account_id,
                'project_id': project_id,
                'dataset': dataset,
                'table_suffix': self._billing_table_suffix(billing_account_id),
                'table_path': f"{project_id}.{dataset}.gcp_billing_export_v1_*",
            })

        return sources

    @staticmethod
    def _billing_table_suffix(billing_account_id: str) -> str:
        """Billing export tables replace dashes in account IDs with underscores."""
        return billing_account_id.replace('-', '_')

    @property
    def _billing_table_suffixes(self) -> List[str]:
        """Return table suffixes for all configured billing accounts."""
        return [
            self._billing_table_suffix(billing_account_id)
            for billing_account_id in self.config.billing_account_ids
        ]

    @staticmethod
    def _sql_quote(value: str) -> str:
        """Quote a string literal for the generated BigQuery SQL."""
        return "'{}'".format(value.replace("'", "''"))

    def _project_filter_sql(self, billing_account_id: str) -> str:
        """Build project filtering SQL for one billing account export source."""
        if self.config.project_billing_account_map:
            configured_project_ids = set(self.config.cost_project_ids)
            project_ids = []
            for project_id, mapped_billing_account_id in self.config.project_billing_account_map.items():
                if mapped_billing_account_id != billing_account_id:
                    continue
                if configured_project_ids and project_id not in configured_project_ids:
                    continue
                project_ids.append(project_id)

            if not project_ids:
                return "\n                    AND FALSE"
        else:
            project_ids = self.config.cost_project_ids

        if project_ids:
            quoted_project_ids = ", ".join(
                self._sql_quote(project_id)
                for project_id in project_ids
            )
            return f"\n                    AND project.id IN ({quoted_project_ids})"

        return ""

    def _initialize_client(self):
        """Initialize GCP BigQuery client"""
        try:
            # Set credentials path as environment variable
            if self.config.credentials_path:
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.config.credentials_path

            # Create credentials and BigQuery client
            credentials = service_account.Credentials.from_service_account_file(
                self.config.credentials_path
            )

            self.client = bigquery.Client(
                project=self.config.billing_export_project_id,
                credentials=credentials
            )
            self.logger.info("GCP BigQuery client initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize GCP BigQuery client: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test GCP BigQuery connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            for source in self._billing_export_sources:
                dataset_path = f"{source['project_id']}.{source['dataset']}"
                self.client.get_dataset(dataset_path)
                self.logger.info(f"GCP BigQuery dataset '{dataset_path}' exists")

                tables = list(self.client.list_tables(dataset_path))
                table_ids = {table.table_id for table in tables}
                expected_table = f"gcp_billing_export_v1_{source['table_suffix']}"

                if not tables:
                    self.logger.warning(
                        f"No billing export tables found yet in {dataset_path}. "
                        "It can take up to 24 hours for data to appear after enabling export. "
                        "Expected table pattern: gcp_billing_export_v1_*"
                    )
                    continue

                if expected_table not in table_ids:
                    self.logger.warning(
                        f"GCP billing export table {expected_table} was not found in "
                        f"{dataset_path}. Verify the billing account ID and export destination."
                    )
                    continue

                query = f"""
                    SELECT COUNT(*) as count
                    FROM `{source['table_path']}`
                    WHERE _TABLE_SUFFIX = {self._sql_quote(source['table_suffix'])}
                      AND billing_account_id = {self._sql_quote(source['billing_account_id'])}
                    LIMIT 1
                """

                list(self.client.query(query).result())

            self.logger.info("GCP BigQuery connection test successful")
            return True
        except Exception as e:
            self.logger.error(f"GCP connection test failed: {e}")
            self.logger.error(
                "Make sure BigQuery billing export is enabled. "
                "See: https://cloud.google.com/billing/docs/how-to/export-data-bigquery"
            )
            return False

    def collect_costs(
        self,
        start_date: date,
        end_date: date
    ) -> List[CostRecord]:
        """
        Collect GCP costs for the specified date range from BigQuery

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of CostRecord objects
        """
        self.logger.info(f"Collecting GCP costs from {start_date} to {end_date}")

        try:
            # Query BigQuery billing export for daily service-level costs
            # This query properly handles CUD costs, savings programs, and credits
            # Costs take a few hours to show up in BigQuery export, might take longer than 24 hours

            # Format dates for the query (YYYY-MM-DD format with timezone)
            start_datetime = f"{start_date.strftime('%Y-%m-%d')}T00:00:00 US/Pacific"
            # Add one day to end_date for exclusive upper bound
            end_datetime = f"{(end_date + timedelta(days=1)).strftime('%Y-%m-%d')}T00:00:00 US/Pacific"

            costs_by_day_and_service = {}
            for source in self._billing_export_sources:
                project_filter = self._project_filter_sql(source['billing_account_id'])
                query = f"""
                    WITH
                      spend_cud_fee_skus AS (
                      SELECT
                        *
                      FROM
                        UNNEST(['5515-81A8-03A2']) AS fee_sku_id ),
                      cost_data AS (
                      SELECT
                        *,
                      IF
                        (sku.id IN (
                          SELECT
                            *
                          FROM
                            spend_cud_fee_skus), cost, 0) AS `spend_cud_fee_cost`,
                        cost - IFNULL(cost_at_effective_price_default, cost) AS `spend_cud_savings`,
                        IFNULL(cost_at_effective_price_default, cost) - cost_at_list AS `negotiated_savings`,
                        IFNULL( (
                          SELECT
                            SUM(CAST(c.amount AS NUMERIC))
                          FROM
                            UNNEST(credits) c
                          WHERE
                            c.type IN ('FEE_UTILIZATION_OFFSET')), 0) AS `cud_credits`,
                        IFNULL( (
                          SELECT
                            SUM(CAST(c.amount AS NUMERIC))
                          FROM
                            UNNEST(credits) c
                          WHERE
                            c.type IN ('SUSTAINED_USAGE_DISCOUNT', 'DISCOUNT')), 0) AS `other_savings`
                      FROM
                        `{source['table_path']}`
                      WHERE
                        _TABLE_SUFFIX = {self._sql_quote(source['table_suffix'])}
                        AND billing_account_id = {self._sql_quote(source['billing_account_id'])}
                        AND cost_type != 'tax'
                        AND cost_type != 'adjustment'
                        AND usage_start_time >= '{start_datetime}'
                        AND usage_start_time < '{end_datetime}'{project_filter} )
                    SELECT
                      DATE(TIMESTAMP_TRUNC(usage_start_time, Day, 'US/Pacific')) AS usage_date,
                      service.description AS service_name,
                      (SUM(CAST(cost AS NUMERIC)) + SUM(CAST(cud_credits AS NUMERIC)) + SUM(CAST(other_savings AS NUMERIC)))
                        / (MAX(currency_conversion_rate) * 1.0) AS cost_usd
                    FROM
                      cost_data
                    GROUP BY
                      usage_date,
                      service_name
                    HAVING
                      cost_usd > 0
                    ORDER BY
                      usage_date DESC,
                      cost_usd DESC
                """

                self.logger.debug(f"Executing BigQuery query: {query}")

                try:
                    query_job = self.client.query(query)
                    results = query_job.result()
                except GoogleAPIError as e:
                    error_msg = str(e)
                    if "does not match any table" in error_msg:
                        self.logger.warning(
                            f"GCP billing export table not found for "
                            f"{source['billing_account_id']} in "
                            f"{source['project_id']}.{source['dataset']}. "
                            "It can take up to 24 hours for data to appear after enabling export."
                        )
                        continue

                    self.logger.error(
                        f"Failed to collect GCP costs for {source['billing_account_id']} "
                        f"from {source['project_id']}.{source['dataset']}: {e}"
                    )
                    continue

                for row in results:
                    service_name = row.service_name or 'Unknown'
                    key = (row.usage_date, service_name)
                    costs_by_day_and_service[key] = (
                        costs_by_day_and_service.get(key, Decimal('0'))
                        + Decimal(str(row.cost_usd))
                    )

            recovery_query = f"""
                SELECT
                  usage_date,
                  service_description AS service_name,
                  SUM(unrounded_subtotal_usd) AS cost_usd
                FROM
                  `disha-ai3.curelink_billing_export_multi.disha_ai2_billing_reports_recovery`
                WHERE
                  usage_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'
                  AND billing_account_id = '016F16-144AD7-8364DE'
                  AND project_id = 'disha-ai2'
                GROUP BY
                  usage_date,
                  service_name
                HAVING
                  cost_usd > 0
            """
            recovery_results = self.client.query(recovery_query).result()

            for row in recovery_results:
                service_name = row.service_name or 'Unknown'
                key = (row.usage_date, service_name)
                costs_by_day_and_service[key] = (
                    costs_by_day_and_service.get(key, Decimal('0'))
                    + Decimal(str(row.cost_usd))
                )

            records = [
                CostRecord(
                    cloud_provider='gcp',
                    service_name=service_name,
                    cost_usd=self._normalize_cost(float(cost_usd)),
                    usage_date=usage_date
                )
                for (usage_date, service_name), cost_usd
                in costs_by_day_and_service.items()
                if cost_usd > 0
            ]
            records.sort(key=lambda record: (record.usage_date, record.cost_usd), reverse=True)

            self._log_collection_summary(start_date, end_date, records)

            return records

        except GoogleAPIError as e:
            error_msg = str(e)
            if "does not match any table" in error_msg:
                self.logger.warning(
                    "GCP billing export tables not found. "
                    "It can take up to 24 hours for data to appear after enabling export."
                )
            else:
                self.logger.error(f"Failed to collect GCP costs via BigQuery: {e}")
                self.logger.warning(
                    "Make sure billing export is enabled and configured correctly. "
                    "See: https://cloud.google.com/billing/docs/how-to/export-data-bigquery"
                )
            # Return empty list instead of failing completely
            return []
        except Exception as e:
            self.logger.error(f"Failed to collect GCP costs: {e}")
            raise
