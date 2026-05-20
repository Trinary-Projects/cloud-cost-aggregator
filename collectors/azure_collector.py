"""
Azure Sponsorship Usage collector
Uses the Microsoft Azure Sponsorships portal API
"""
from datetime import date, timedelta
from typing import List, Dict
from decimal import Decimal
import requests
import json

from collectors.base_collector import BaseCollector, CostRecord
from config import AzureConfig


class AzureCollector(BaseCollector):
    """
    Collector for Azure Sponsorship costs
    Uses the Microsoft Azure Sponsorships portal API
    """

    def __init__(self, config: AzureConfig):
        """
        Initialize Azure collector

        Args:
            config: Azure configuration
        """
        super().__init__('azure')
        self.config = config
        self.api_url = "https://www.microsoftazuresponsorships.com/Usage/GetSubscriptionData"

    def test_connection(self) -> bool:
        """
        Test Azure Sponsorship API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Test with a small date range
            test_start = date.today() - timedelta(days=7)
            test_end = date.today()

            params = {
                'startDate': test_start.strftime('%Y-%m-%d'),
                'endDate': test_end.strftime('%Y-%m-%d'),
                'subscriptionGuid': self.config.subscription_id
            }

            headers = self._get_headers()
            response = requests.get(self.api_url, params=params, headers=headers, timeout=30)

            if response.status_code == 200:
                self.logger.info("Azure Sponsorship API connection test successful")
                return True
            else:
                self.logger.error(f"Azure connection test failed: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Azure connection test failed: {e}")
            return False

    def collect_costs(
        self,
        start_date: date,
        end_date: date
    ) -> List[CostRecord]:
        """
        Collect Azure Sponsorship costs for the specified date range
        Makes separate API calls for each day since API returns aggregated data

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of CostRecord objects
        """
        self.logger.info(f"Collecting Azure Sponsorship costs from {start_date} to {end_date}")

        try:
            all_records = []
            current_date = start_date

            # Azure API returns aggregated data for entire range
            # So we need to call it separately for each day
            while current_date <= end_date:
                self.logger.debug(f"Fetching Azure costs for {current_date}")

                params = {
                    'startDate': current_date.strftime('%Y-%m-%d'),
                    'endDate': current_date.strftime('%Y-%m-%d'),
                    'subscriptionGuid': self.config.subscription_id
                }

                headers = self._get_headers()
                response = requests.get(self.api_url, params=params, headers=headers, timeout=60)
                self.logger.info(f"Azure response: {response.text}")

                if response.status_code != 200:
                    self.logger.error(
                        f"Azure API returned status {response.status_code} for {current_date}: {response.text}"
                    )
                    current_date += timedelta(days=1)
                    continue

                data = response.json()
                daily_records = self._parse_response(data, current_date)
                all_records.extend(daily_records)

                current_date += timedelta(days=1)

            self._log_collection_summary(start_date, end_date, all_records)

            return all_records

        except Exception as e:
            self.logger.error(f"Failed to collect Azure Sponsorship costs: {e}")
            raise

    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers with cookies for Azure Sponsorship API

        Returns:
            Dictionary of headers
        """
        return {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cookie': self.config.sponsorship_cookies,
            'DNT': '1',
            'Referer': 'https://www.microsoftazuresponsorships.com/Usage',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        }

    def _parse_response(
        self,
        data: Dict,
        usage_date: date
    ) -> List[CostRecord]:
        """
        Parse Azure Sponsorship API response for a single day

        The API returns data in format:
        {
            "TableHeaders": ["Service Name", "Service Resource", "Spend"],
            "TableRows": [
                ["Cognitive Services", "S1 Speech To Text", "$2,354.00"],
                ["Cognitive Services", "gpt-4o-0806-Inp-glbl Tokens", "$820.60"],
                ...
            ]
        }

        Args:
            data: API response JSON
            usage_date: Date to assign costs to

        Returns:
            List of CostRecord objects
        """
        records = []

        table_rows = data.get('TableRows', [])
        if not table_rows:
            self.logger.debug(f"No Azure Sponsorship usage data for {usage_date}")
            return records

        # Group costs by normalized service name
        service_costs = {}

        for row in table_rows:
            try:
                if len(row) < 3:
                    continue

                # Parse row: [Service Name, Service Resource, Spend]
                service_name = row[0]
                service_resource = row[1]
                spend_str = row[2]

                # Normalize service name based on resource type
                normalized_service = self._normalize_service_name(service_name, service_resource)

                # Parse cost: Remove "$" and "," from string like "$2,354.00"
                cost_str = spend_str.replace('$', '').replace(',', '')
                cost_amount = float(cost_str)

                # Skip zero-cost services
                if cost_amount == 0:
                    continue

                # Aggregate costs by normalized service name
                if normalized_service in service_costs:
                    service_costs[normalized_service] += cost_amount
                else:
                    service_costs[normalized_service] = cost_amount

            except (ValueError, IndexError, TypeError) as e:
                self.logger.warning(f"Failed to parse Azure usage row: {row}. Error: {e}")
                continue

        # Create cost records from aggregated data
        for service_name, total_cost in service_costs.items():
            record = CostRecord(
                cloud_provider='azure',
                service_name=service_name,
                cost_usd=self._normalize_cost(total_cost),
                usage_date=usage_date
            )
            records.append(record)

        return records

    def _normalize_service_name(self, service_name: str, service_resource: str) -> str:
        """
        Normalize Azure service names to group related resources

        Args:
            service_name: Service category (e.g., "Cognitive Services")
            service_resource: Specific resource (e.g., "gpt-4o-0806-Inp-glbl Tokens")

        Returns:
            Normalized service name
        """
        resource_lower = service_resource.lower()

        # Azure OpenAI models
        if any(model in resource_lower for model in ['gpt', 'chatgpt', 'davinci', 'embedding', 'ada']):
            return "Azure OpenAI"

        # Speech Services
        if 'speech to text' in resource_lower or 'stt' in resource_lower:
            return "Azure Speech-to-Text"

        if 'text to speech' in resource_lower or 'tts' in resource_lower or 'neural' in resource_lower:
            return "Azure Text-to-Speech"

        # Default: Use service name
        return service_name
