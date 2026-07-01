# Cloud Cost Aggregator

A Python-based tool to aggregate and track cloud usage costs from AWS, GCP, and Azure. Collects daily service-level cost data and stores it in PostgreSQL for analysis and reporting.

## Features

- **Multi-Cloud Support**: Collects costs from AWS, GCP, and Azure
- **Service-Level Granularity**: Tracks costs broken down by individual services
- **Daily Cost Tracking**: Maintains daily cost history for trend analysis
- **Automatic Upserts**: Handles cost updates as cloud providers finalize billing data
- **T-2 Day Lookback**: Accounts for cloud billing data materialization delays (costs from 2 days ago)
- **Historical Backfill**: Supports backfilling up to 90 days of historical data
- **Normalized Pricing**: All costs stored in USD for consistency
- **Credit Handling**: Excludes credits and refunds to show actual usage costs
- **Parallel Collection**: Collects from all providers simultaneously for speed

## Architecture

```
cloud_cost_aggregator/
├── collectors/              # Cloud provider collectors
│   ├── base_collector.py   # Base class for all collectors
│   ├── aws_collector.py    # AWS Cost Explorer integration
│   ├── gcp_collector.py    # GCP BigQuery billing export
│   └── azure_collector.py  # Azure Sponsorship portal API
├── database/               # Database layer
│   ├── connection.py       # Database connection management
│   ├── models.py          # SQLAlchemy models
│   └── schema.sql         # PostgreSQL schema
├── utils/                 # Utility functions
│   ├── logger.py         # Logging configuration
│   └── date_utils.py     # Date range utilities
├── aggregator.py         # Main aggregation orchestrator
├── config.py            # Configuration management
├── main.py             # CLI entry point
└── requirements.txt    # Python dependencies
```

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Cloud provider accounts with appropriate permissions:
  - AWS: Cost Explorer API access
  - GCP: BigQuery billing export enabled
  - Azure: Valid sponsorship or subscription

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/cloud-cost-aggregator.git
cd cloud-cost-aggregator
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup PostgreSQL database

Create the database:
```bash
# Using createdb
createdb cloud_costs

# Or using psql
psql -U postgres -c "CREATE DATABASE cloud_costs;"
```

Initialize the schema:
```bash
# Using psql
psql -U postgres -d cloud_costs -f database/schema.sql

# Or using the CLI
python main.py --init-db
```

### 5. Configure environment variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials (see Configuration section below).

## Configuration

### Environment Variables

Edit the `.env` file with your credentials:

```bash
# PostgreSQL Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cloud_costs
DB_USER=postgres
DB_PASSWORD=your_password_here

# AWS Credentials
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=us-east-1

# GCP Credentials
GCP_BILLING_ACCOUNT_IDS=XXXXXX-YYYYYY-ZZZZZZ,AAAAAA-BBBBBB-CCCCCC
GCP_BILLING_EXPORT_PROJECT_ID=your-billing-export-project-id
GCP_CREDENTIALS_PATH=/path/to/service-account.json
GCP_BIGQUERY_DATASET=billing_export
GCP_COST_PROJECT_IDS=your-claude-project-id,another-project-id
GCP_PROJECT_BILLING_ACCOUNT_MAP=your-claude-project-id:XXXXXX-YYYYYY-ZZZZZZ,another-project-id:AAAAAA-BBBBBB-CCCCCC
GCP_BILLING_EXPORT_LOCATION_MAP=XXXXXX-YYYYYY-ZZZZZZ:your-billing-export-project-id.billing_export,AAAAAA-BBBBBB-CCCCCC:another-export-project.another_billing_export_dataset

# Azure Credentials
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=your-secret-value-here
AZURE_SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Azure Sponsorship Cookies (for Azure for Students/Startups)
AZURE_SPONSORSHIP_COOKIES=your_cookies_here

# Optional Configuration
LOG_LEVEL=INFO
LOOKBACK_DAYS=2
BACKFILL_DAYS=90
```

### AWS Setup

1. **Create IAM user** with Cost Explorer permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

2. **Enable Cost Explorer** in the AWS Console (if not already enabled)
3. **Create access key** and add credentials to `.env` file

### GCP Setup

1. **Enable billing export to BigQuery**:

```bash
# Create dataset for billing export
bq mk --dataset --location=US billing_export
```

Then in GCP Console:
- Go to **Billing → Billing export → BigQuery export**
- Enable "Detailed usage cost" export
- Set dataset to: `billing_export`
- Choose the Cloud Billing account that pays for your Claude project
- Store the export in the BigQuery project configured as `GCP_BILLING_EXPORT_PROJECT_ID`

2. **Create service account and grant permissions**:

```bash
# Create service account
gcloud iam service-accounts create cloud-cost-reader \
  --display-name="Cloud Cost Reader"

# Grant BigQuery permissions
gcloud projects add-iam-policy-binding YOUR_BILLING_EXPORT_PROJECT_ID \
  --member="serviceAccount:cloud-cost-reader@YOUR_BILLING_EXPORT_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.user"

gcloud projects add-iam-policy-binding YOUR_BILLING_EXPORT_PROJECT_ID \
  --member="serviceAccount:cloud-cost-reader@YOUR_BILLING_EXPORT_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

# Create and download key
gcloud iam service-accounts keys create gcp-credentials.json \
  --iam-account=cloud-cost-reader@YOUR_BILLING_EXPORT_PROJECT_ID.iam.gserviceaccount.com
```

3. **Update `.env`** with the path to `gcp-credentials.json`

**Important**:
- `GCP_BILLING_EXPORT_PROJECT_ID` is the BigQuery project that hosts the billing export dataset. This is what the code queries.
- `GCP_BILLING_ACCOUNT_IDS` identifies which billing account tables to read from inside that dataset. Use a comma-separated list if tracked projects are billed through multiple billing accounts.
- `GCP_BILLING_ACCOUNT_ID` is still supported as a backward-compatible alias for a single billing account.
- `GCP_BILLING_EXPORT_LOCATION_MAP` should be set when billing accounts export to different BigQuery project/dataset locations. Format: `billing-account-id:project.dataset,billing-account-id:project.dataset`. If omitted for an account, the collector falls back to `GCP_BILLING_EXPORT_PROJECT_ID.GCP_BIGQUERY_DATASET`.
- `GCP_COST_PROJECT_IDS` should be set to the actual Claude workload project IDs if you want costs scoped to specific GCP projects instead of every project attached to the billing account. Use a comma-separated list for multiple projects.
- `GCP_PROJECT_BILLING_ACCOUNT_MAP` should be set when tracked projects are spread across billing accounts. It prevents old/new billing account overlap from double counting migration days.
- `GCP_COST_PROJECT_ID` is still supported as a backward-compatible alias for a single tracked project.
- `GCP_PROJECT_ID` is still supported as a backward-compatible alias for `GCP_BILLING_EXPORT_PROJECT_ID`.

**Note**: It can take up to 24 hours for billing data to appear in BigQuery after enabling export.

### Azure Setup

#### For Standard Subscriptions:

```bash
# Create service principal
az ad sp create-for-rbac --name "cloud-cost-reader"

# Grant Cost Management Reader role
az role assignment create \
  --assignee <client-id> \
  --role "Cost Management Reader" \
  --scope /subscriptions/<subscription-id>
```

#### For Azure Sponsorships (Students/Startups):

Azure Sponsorship accounts don't support the Cost Management API, so we use a cookie-based approach:

1. Log in to [Azure Sponsorship Portal](https://www.microsoftazuresponsorships.com/Usage)
2. Open browser DevTools (F12) → Network tab
3. Refresh the page
4. Find any API request and copy the entire `Cookie` header value
5. Add to `.env` as `AZURE_SPONSORSHIP_COOKIES`

**Note**: Cookies expire periodically and need to be refreshed.

## Usage

### Test Connections

Before running cost collection, verify all cloud provider connections:

```bash
python main.py --test-connections
```

Test specific providers:
```bash
python main.py --test-connections --providers aws,gcp
```

### Daily Cost Collection

Run daily collection with T-2 lookback (recommended for cron jobs):

```bash
python main.py
```

This collects costs from 2 days ago, accounting for billing data materialization delays.

### Historical Backfill

Backfill 90 days of historical data:

```bash
python main.py --backfill
```

Custom backfill period:
```bash
python main.py --backfill --start-date 2024-10-01 --end-date 2024-11-01
```

### Custom Date Ranges

Collect costs for specific date range:

```bash
python main.py --start-date 2024-11-01 --end-date 2024-11-08
```

### Provider Selection

Collect from specific providers only:

```bash
python main.py --providers aws,azure
```

### Initialize Database

Create database tables:

```bash
python main.py --init-db
```

## Setting Up Automation

### Linux/macOS (Cron)

Add to crontab (`crontab -e`):

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/cloud-cost-aggregator && /path/to/venv/bin/python main.py >> /var/log/cloud-costs.log 2>&1
```

Run twice daily to catch cost updates:
```bash
# Morning run at 2 AM
0 2 * * * cd /path/to/cloud-cost-aggregator && /path/to/venv/bin/python main.py >> /var/log/cloud-costs.log 2>&1

# Evening run at 2 PM
0 14 * * * cd /path/to/cloud-cost-aggregator && /path/to/venv/bin/python main.py >> /var/log/cloud-costs.log 2>&1
```

### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start a program
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\path\to\cloud-cost-aggregator`

## Database Schema

### Main Table: `cloud_costs`

```sql
CREATE TABLE cloud_costs (
    id SERIAL PRIMARY KEY,
    cloud_provider VARCHAR(50) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    cost_usd DECIMAL(12, 2) NOT NULL,
    usage_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cloud_provider, service_name, usage_date)
);
```

The `UNIQUE` constraint enables automatic upserts when costs are updated.

| Column          | Type         | Description                      |
|-----------------|--------------|----------------------------------|
| id              | SERIAL       | Primary key                      |
| cloud_provider  | VARCHAR(50)  | 'aws', 'gcp', or 'azure'         |
| service_name    | VARCHAR(255) | Service name (e.g., 'EC2', 'S3') |
| cost_usd        | DECIMAL      | Cost in USD (2 decimal places)   |
| usage_date      | DATE         | Date the cost occurred           |
| created_at      | TIMESTAMP    | Record creation timestamp        |
| updated_at      | TIMESTAMP    | Last update timestamp            |

### Views

The schema includes helpful views for common queries:

**`daily_cost_summary`** - Daily totals by provider
**`service_cost_summary`** - Service-level aggregates

## Querying Cost Data

### Example SQL Queries

**Total costs by provider (last 30 days):**
```sql
SELECT
    cloud_provider,
    SUM(cost_usd) as total_cost
FROM cloud_costs
WHERE usage_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY cloud_provider
ORDER BY total_cost DESC;
```

**Top 10 most expensive services:**
```sql
SELECT
    cloud_provider,
    service_name,
    SUM(cost_usd) as total_cost
FROM cloud_costs
WHERE usage_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY cloud_provider, service_name
ORDER BY total_cost DESC
LIMIT 10;
```

**Daily cost trend:**
```sql
SELECT
    usage_date,
    cloud_provider,
    SUM(cost_usd) as daily_cost
FROM cloud_costs
WHERE usage_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY usage_date, cloud_provider
ORDER BY usage_date DESC, cloud_provider;
```

**Monthly cost comparison:**
```sql
SELECT
    DATE_TRUNC('month', usage_date) as month,
    cloud_provider,
    SUM(cost_usd) as monthly_cost
FROM cloud_costs
GROUP BY month, cloud_provider
ORDER BY month DESC, cloud_provider;
```

## Service Name Normalization

### Azure Services

The Azure collector normalizes service names for better grouping:

- **Azure OpenAI**: All GPT, ChatGPT, Davinci, Embedding, and Ada models
- **Azure Speech-to-Text**: All speech-to-text and STT services
- **Azure Text-to-Speech**: All text-to-speech, TTS, and neural voice services

### AWS & GCP

Service names are preserved as returned by the respective APIs.

## Troubleshooting

### AWS: No data or incorrect costs

**Issue**: AWS costs showing as $0 or negative values

**Solution**: The tool automatically excludes credits and refunds using the `Filter` parameter. This shows actual usage costs. AWS data can take 24-48 hours to fully materialize.

### GCP: "does not match any table"

**Issue**: BigQuery billing export tables not found

**Solution**:
- Verify billing export is enabled in GCP Console
- Wait up to 24 hours for initial data to populate
- Check dataset name matches `GCP_BIGQUERY_DATASET` in `.env`
- Verify service account has `bigquery.user` and `bigquery.dataViewer` roles

### Azure: 401 Unauthorized or empty data

**Issue**: Azure Sponsorship API returns authentication errors

**Solution**:
1. Cookies have expired - refresh them from browser
2. Log in to Azure Sponsorship portal
3. Open DevTools (F12) → Network tab
4. Find an API request and copy the Cookie header
5. Update `AZURE_SPONSORSHIP_COOKIES` in `.env`

**Issue**: Azure returns aggregated data for date ranges

**Solution**: The collector automatically makes separate API calls for each day in the range to ensure daily granularity.

### Database Connection Failed

**Issue**: Cannot connect to PostgreSQL

**Solution**:
```bash
# Check PostgreSQL is running
pg_isready

# Test connection manually
psql -h localhost -U postgres -d cloud_costs

# Verify credentials in .env match your PostgreSQL setup
```

### Rate Limiting

**Issue**: API rate limits exceeded

**Solution**:
- Run providers separately: `--providers aws` then `--providers gcp`, etc.
- The tool already uses parallel collection which should be within limits
- Check your cloud provider's API quota limits

## Cost Considerations

Running this tool incurs minimal cloud costs:

- **AWS Cost Explorer API**: $0.01 per API request (typically 1-2 requests per run)
- **GCP BigQuery**: Billed per query (usually < $0.01 per run with small billing data)
- **Azure**: Sponsorship portal API is free

**Estimated monthly cost**: $0.50-$1.00 per month in API charges for daily runs.

## Security Notes

- **Never commit `.env` file** - it contains sensitive credentials
- `.env` is already in `.gitignore` - verify before committing
- Store credentials securely (use secret management tools in production)
- Rotate Azure sponsorship cookies regularly
- Use IAM roles with minimal required permissions
- Enable MFA on cloud provider accounts
- Consider using AWS Secrets Manager, GCP Secret Manager, or Azure Key Vault for production

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing issues for solutions
- Refer to cloud provider documentation for API-specific questions

## Roadmap

Future enhancements:

- [ ] Add support for Oracle Cloud Infrastructure (OCI)
- [ ] Implement cost anomaly detection and alerts
- [ ] Add web dashboard for visualization
- [ ] Support for multiple AWS accounts
- [ ] Export to CSV/Excel
- [ ] Slack/email notifications for cost spikes
- [ ] Budget alerts and thresholds
- [ ] Cost forecasting using historical data
- [ ] Tag-based cost allocation
- [ ] Docker containerization

## Acknowledgments

Built to help teams track and optimize their multi-cloud spending.

---

**Last Updated**: November 2024
