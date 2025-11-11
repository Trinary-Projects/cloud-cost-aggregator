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
                project=self.config.project_id,
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
            # First check if dataset exists
            dataset_ref = self.client.get_dataset(
                f"{self.config.project_id}.{self.config.bigquery_dataset}"
            )
            self.logger.info(f"GCP BigQuery dataset '{self.config.bigquery_dataset}' exists")

            # Try to list tables in the dataset
            tables = list(self.client.list_tables(
                f"{self.config.project_id}.{self.config.bigquery_dataset}"
            ))

            if not tables:
                self.logger.warning(
                    "No billing export tables found yet. "
                    "It can take up to 24 hours for data to appear after enabling export. "
                    "Expected table pattern: gcp_billing_export_v1_*"
                )
                return True  # Dataset exists, just waiting for data

            # Try to query the billing export table
            query = f"""
                SELECT COUNT(*) as count
                FROM `{self.config.project_id}.{self.config.bigquery_dataset}.gcp_billing_export_v1_*`
                LIMIT 1
            """

            query_job = self.client.query(query)
            results = list(query_job.result())

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

            query = f"""
                WITH
                  spend_cud_fee_skus AS (
                  SELECT
                    *
                  FROM
                    UNNEST(['']) AS fee_sku_id ),
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
                        c.type IN ('')), 0) AS `cud_credits`,
                    IFNULL( (
                      SELECT
                        SUM(CAST(c.amount AS NUMERIC))
                      FROM
                        UNNEST(credits) c
                      WHERE
                        c.type IN ('')), 0) AS `other_savings`
                  FROM
                    `{self.config.project_id}.{self.config.bigquery_dataset}.gcp_billing_export_v1_*`
                  WHERE
                    cost_type != 'tax'
                    AND cost_type != 'adjustment'
                    AND usage_start_time >= '{start_datetime}'
                    AND usage_start_time < '{end_datetime}' )
                SELECT
                  DATE(TIMESTAMP_TRUNC(usage_start_time, Day, 'US/Pacific')) AS usage_date,
                  service.description AS service_name,
                  SUM(CAST(IFNULL(cost_at_effective_price_default, cost) AS NUMERIC)) - SUM(CAST(spend_cud_fee_cost AS NUMERIC)) AS cost_usd
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

            # Execute query
            query_job = self.client.query(query)
            results = query_job.result()

            # Parse results
            records = []
            for row in results:
                record = CostRecord(
                    cloud_provider='gcp',
                    service_name=row.service_name or 'Unknown',
                    cost_usd=self._normalize_cost(float(row.cost_usd)),
                    usage_date=row.usage_date
                )
                records.append(record)

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
