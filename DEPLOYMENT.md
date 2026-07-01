# Docker Deployment Guide

This guide covers deploying the Cloud Cost Aggregator using Docker.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- `.prod.env` file with production credentials
- `gke-credentials.json` file for GCP access

## Quick Start

### 1. Prepare Production Files

Ensure you have the following files in the project root:

- `.prod.env` - Production environment variables
- `gke-credentials.json` - GCP service account credentials

### 2. Build and Run

```bash
# Build the Docker image
docker-compose build

# Run the container
docker-compose up -d

# View logs
docker-compose logs -f
```

### 3. Run Cost Collection

```bash
# Run daily collection (T-2 days)
docker-compose run --rm cloud-cost-aggregator python main.py

# Run with backfill
docker-compose run --rm cloud-cost-aggregator python main.py --backfill

# Test connections
docker-compose run --rm cloud-cost-aggregator python main.py --test-connections

# Run for specific date range
docker-compose run --rm cloud-cost-aggregator python main.py --start-date 2024-11-01 --end-date 2024-11-10
```

## Production Environment Variables

Your `.prod.env` file should contain:

```bash
# PostgreSQL Database
DB_HOST=your-prod-host
DB_PORT=5432
DB_NAME=cloud_costs
DB_USER=your-user
DB_PASSWORD=your-password

# AWS Credentials
AWS_ACCESS_KEY_ID=your-key-id
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# GCP Credentials
GCP_BILLING_ACCOUNT_IDS=XXXXXX-YYYYYY-ZZZZZZ,AAAAAA-BBBBBB-CCCCCC
GCP_BILLING_EXPORT_PROJECT_ID=your-billing-export-project-id
GCP_CREDENTIALS_PATH=./gke-credentials.json
GCP_BIGQUERY_DATASET=billing_export
GCP_COST_PROJECT_IDS=your-claude-project-id,another-project-id
GCP_PROJECT_BILLING_ACCOUNT_MAP=your-claude-project-id:XXXXXX-YYYYYY-ZZZZZZ,another-project-id:AAAAAA-BBBBBB-CCCCCC
GCP_BILLING_EXPORT_LOCATION_MAP=XXXXXX-YYYYYY-ZZZZZZ:your-billing-export-project-id.billing_export,AAAAAA-BBBBBB-CCCCCC:another-export-project.another_billing_export_dataset

# Azure Credentials
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_SPONSORSHIP_COOKIES=your-cookies-here

# Sentry (already set in docker-compose.yml)
# SENTRY_DSN will be injected by docker-compose

# Optional Configuration
LOG_LEVEL=INFO
LOOKBACK_DAYS=2
BACKFILL_DAYS=90
```

## Scheduled Execution

### Using Cron (Linux/macOS)

Add to crontab (`crontab -e`):

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/cloud-cost-aggregator && docker-compose run --rm cloud-cost-aggregator python main.py >> /var/log/cloud-costs-docker.log 2>&1
```

### Using systemd Timer (Linux)

Create `/etc/systemd/system/cloud-costs.service`:

```ini
[Unit]
Description=Cloud Cost Aggregator
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/cloud-cost-aggregator
ExecStart=/usr/bin/docker-compose run --rm cloud-cost-aggregator python main.py

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/cloud-costs.timer`:

```ini
[Unit]
Description=Run Cloud Cost Aggregator daily
Requires=cloud-costs.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable cloud-costs.timer
sudo systemctl start cloud-costs.timer
sudo systemctl status cloud-costs.timer
```

### Using Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start a program
   - Program: `C:\Program Files\Docker\Docker\resources\bin\docker-compose.exe`
   - Arguments: `run --rm cloud-cost-aggregator python main.py`
   - Start in: `C:\path\to\cloud-cost-aggregator`

## Docker Commands

### Build and Management

```bash
# Build image
docker-compose build

# Build without cache
docker-compose build --no-cache

# Start container
docker-compose up -d

# Stop container
docker-compose down

# View logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100

# Remove all containers and volumes
docker-compose down -v
```

### Running Commands

```bash
# Run one-time collection
docker-compose run --rm cloud-cost-aggregator python main.py

# Run with custom arguments
docker-compose run --rm cloud-cost-aggregator python main.py --providers aws,gcp

# Access container shell
docker-compose run --rm cloud-cost-aggregator /bin/bash

# Run tests
docker-compose run --rm cloud-cost-aggregator python main.py --test-connections
```

## Monitoring

### Sentry Integration

The application automatically sends errors and performance data to Sentry. The DSN is configured in `docker-compose.yml`:

- Dashboard: https://sentry.io/organizations/your-org/
- Errors will be tracked automatically
- Performance metrics are sampled at 100%

### Logs

View logs in real-time:
```bash
docker-compose logs -f cloud-cost-aggregator
```

Logs are rotated automatically:
- Max size: 10MB per file
- Max files: 3
- Total max storage: ~30MB

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs cloud-cost-aggregator
```

Verify credentials:
```bash
docker-compose run --rm cloud-cost-aggregator python main.py --test-connections
```

### Database connection issues

Ensure PostgreSQL is accessible from Docker:
```bash
# Test connection
docker-compose run --rm cloud-cost-aggregator python -c "import psycopg2; print('OK')"
```

If using `localhost`, change to `host.docker.internal` (Docker Desktop) or the actual host IP.

### GCP credentials not found

Ensure `gke-credentials.json` exists:
```bash
docker-compose run --rm cloud-cost-aggregator ls -la gke-credentials.json
```

### Sentry not working

Check if Sentry DSN is set:
```bash
docker-compose run --rm cloud-cost-aggregator python -c "import os; print(os.getenv('SENTRY_DSN'))"
```

## Security Notes

- Never commit `.prod.env` or `gke-credentials.json` to Git
- Use Docker secrets in production environments
- Run container as non-root user (already configured)
- Keep base images updated: `docker-compose pull`
- Scan for vulnerabilities: `docker scan cloud-cost-aggregator`

## Updating

Pull latest code and rebuild:

```bash
git pull origin main
docker-compose build
docker-compose up -d
```

## Cleanup

Remove all containers, images, and volumes:

```bash
docker-compose down -v --rmi all
```

## Production Checklist

- [ ] `.prod.env` file created with production credentials
- [ ] `gke-credentials.json` file placed in project root
- [ ] Database accessible from Docker container
- [ ] Sentry DSN configured and verified
- [ ] Test connections successful
- [ ] Scheduled task/cron job configured
- [ ] Log rotation configured
- [ ] Monitoring alerts set up
- [ ] Backup strategy for PostgreSQL database

---

For issues or questions, refer to the main README.md or open a GitHub issue.
