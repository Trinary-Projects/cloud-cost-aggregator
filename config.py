"""
Configuration management for cloud cost aggregator
Loads settings from environment variables
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv
from utils.aws_ssm import get_ssm_parameter

# Load environment variables from .env file
load_dotenv()


@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def url(self) -> str:
        """Build PostgreSQL connection URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class AWSConfig:
    """AWS configuration"""
    access_key_id: str
    secret_access_key: str
    region: str


@dataclass
class GCPConfig:
    """GCP configuration"""
    billing_account_id: str
    project_id: str
    credentials_path: str
    bigquery_dataset: str  # BigQuery dataset for billing export (e.g., "billing_export")


@dataclass
class AzureConfig:
    """Azure configuration"""
    tenant_id: str
    client_id: str
    client_secret: str
    subscription_id: str
    sponsorship_cookies: str  # Cookies for Azure Sponsorship portal


@dataclass
class AppConfig:
    """Application configuration"""
    log_level: str
    lookback_days: int
    backfill_days: int


class Config:
    """
    Main configuration class
    """

    def __init__(self):
        self.database = self._load_database_config()
        self.aws = self._load_aws_config()
        self.gcp = self._load_gcp_config()
        self.azure = self._load_azure_config()
        self.app = self._load_app_config()

    @staticmethod
    def _load_database_config() -> DatabaseConfig:
        """Load database configuration from environment"""
        return DatabaseConfig(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            name=os.getenv('DB_NAME', 'cloud_costs'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', '')
        )

    @staticmethod
    def _load_aws_config() -> AWSConfig:
        """Load AWS configuration from environment"""
        return AWSConfig(
            access_key_id=os.getenv('AWS_ACCESS_KEY_ID', ''),
            secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', ''),
            region=os.getenv('AWS_REGION', 'us-east-1')
        )

    @staticmethod
    def _load_gcp_config() -> GCPConfig:
        """Load GCP configuration from environment"""
        return GCPConfig(
            billing_account_id=os.getenv('GCP_BILLING_ACCOUNT_ID', ''),
            project_id=os.getenv('GCP_PROJECT_ID', ''),
            credentials_path=os.getenv('GCP_CREDENTIALS_PATH',
                                      os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')),
            bigquery_dataset=os.getenv('GCP_BIGQUERY_DATASET', 'billing_export')
        )

    @staticmethod
    def _load_azure_config() -> AzureConfig:
        """Load Azure configuration from environment and AWS SSM"""
        # Fetch sponsorship cookies from AWS Systems Manager
        sponsorship_cookies = ''
        try:
            sponsorship_cookies = get_ssm_parameter('/cloud_cost_aggregator/AZURE_SPONSORSHIP_COOKIES')
        except Exception as e:
            # Log warning but continue - will fail validation later if cookies are truly required
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to fetch AZURE_SPONSORSHIP_COOKIES from AWS SSM: {e}")
            # Fallback to environment variable if SSM fetch fails
            sponsorship_cookies = os.getenv('AZURE_SPONSORSHIP_COOKIES', '')

        return AzureConfig(
            tenant_id=os.getenv('AZURE_TENANT_ID', ''),
            client_id=os.getenv('AZURE_CLIENT_ID', ''),
            client_secret=os.getenv('AZURE_CLIENT_SECRET', ''),
            subscription_id=os.getenv('AZURE_SUBSCRIPTION_ID', ''),
            sponsorship_cookies=sponsorship_cookies
        )

    @staticmethod
    def _load_app_config() -> AppConfig:
        """Load application configuration from environment"""
        return AppConfig(
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            lookback_days=int(os.getenv('LOOKBACK_DAYS', '2')),
            backfill_days=int(os.getenv('BACKFILL_DAYS', '90'))
        )

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of errors

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate database config
        if not self.database.password:
            errors.append("DB_PASSWORD is required")

        # Validate AWS config
        if not self.aws.access_key_id or not self.aws.secret_access_key:
            errors.append("AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) are required")

        # Validate GCP config
        if not self.gcp.billing_account_id:
            errors.append("GCP_BILLING_ACCOUNT_ID is required")
        if not self.gcp.project_id:
            errors.append("GCP_PROJECT_ID is required")
        if not self.gcp.credentials_path:
            errors.append("GCP_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS is required")

        # Validate Azure config
        if not self.azure.tenant_id:
            errors.append("AZURE_TENANT_ID is required")
        if not self.azure.client_id:
            errors.append("AZURE_CLIENT_ID is required")
        if not self.azure.client_secret:
            errors.append("AZURE_CLIENT_SECRET is required")
        if not self.azure.subscription_id:
            errors.append("AZURE_SUBSCRIPTION_ID is required")

        return errors


# Global config instance
config = Config()
