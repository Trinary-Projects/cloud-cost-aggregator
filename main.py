#!/usr/bin/env python3
"""
Cloud Cost Aggregator - Main entry point
Collects and aggregates cloud costs from AWS, GCP, and Azure
"""
import argparse
import sys
from datetime import date

from config import config
from database.connection import DatabaseManager, build_database_url
from aggregator import CostAggregator
from utils.logger import setup_logger
from utils.date_utils import get_date_range, parse_date_string


def parse_arguments():
    """
    Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Cloud Cost Aggregator - Collect costs from AWS, GCP, and Azure'
    )

    parser.add_argument(
        '--backfill',
        action='store_true',
        help='Backfill historical data (past 90 days by default)'
    )

    parser.add_argument(
        '--backfill-days',
        type=int,
        help='Number of days to backfill (implies --backfill if set)'
    )

    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date in YYYY-MM-DD format (overrides default T-2)'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        help='End date in YYYY-MM-DD format (overrides default T-2)'
    )

    parser.add_argument(
        '--providers',
        type=str,
        help='Comma-separated list of providers (aws,gcp,azure). Default: all'
    )

    parser.add_argument(
        '--test-connections',
        action='store_true',
        help='Test connections to all cloud providers and exit'
    )

    parser.add_argument(
        '--init-db',
        action='store_true',
        help='Initialize database tables and exit'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level (default: INFO)'
    )

    return parser.parse_args()


def main():
    """
    Main execution function
    """
    # Parse arguments
    args = parse_arguments()

    # Setup logging
    log_level = args.log_level or config.app.log_level
    logger = setup_logger(level=log_level)

    logger.info("=" * 60)
    logger.info("Cloud Cost Aggregator")
    logger.info("=" * 60)

    # Validate configuration
    logger.info("Validating configuration...")
    errors = config.validate()
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("Please check your .env file")
        sys.exit(1)

    logger.info("Configuration validated successfully")

    # Initialize database manager
    db_manager = DatabaseManager(config.database.url)
    db_manager.initialize()

    # Handle --init-db flag
    if args.init_db:
        logger.info("Initializing database tables...")
        db_manager.create_tables()
        logger.info("Database initialized successfully")
        sys.exit(0)

    # Test database connection
    if not db_manager.test_connection():
        logger.error("Database connection failed. Please check your configuration.")
        sys.exit(1)

    # Initialize aggregator
    aggregator = CostAggregator(config, db_manager)

    # Handle --test-connections flag
    if args.test_connections:
        logger.info("Testing cloud provider connections...")
        results = aggregator.test_all_connections()

        all_passed = True
        for provider, status in results.items():
            status_str = "✓ PASS" if status else "✗ FAIL"
            logger.info(f"{provider.upper()}: {status_str}")
            if not status:
                all_passed = False

        sys.exit(0 if all_passed else 1)

    # Parse date range
    start_date = None
    end_date = None

    if args.start_date:
        try:
            start_date = parse_date_string(args.start_date)
        except ValueError:
            logger.error(f"Invalid start date format: {args.start_date}. Use YYYY-MM-DD")
            sys.exit(1)

    if args.end_date:
        try:
            end_date = parse_date_string(args.end_date)
        except ValueError:
            logger.error(f"Invalid end date format: {args.end_date}. Use YYYY-MM-DD")
            sys.exit(1)

    # Determine backfill settings
    # --backfill-days implies --backfill mode
    backfill_enabled = args.backfill or args.backfill_days is not None
    backfill_days = args.backfill_days if args.backfill_days is not None else config.app.backfill_days

    # Get date range
    start_date, end_date = get_date_range(
        backfill=backfill_enabled,
        lookback_days=config.app.lookback_days,
        backfill_days=backfill_days,
        start_date=start_date,
        end_date=end_date
    )

    logger.info(f"Date range: {start_date} to {end_date}")

    # Parse providers
    providers = None
    if args.providers:
        providers = [p.strip().lower() for p in args.providers.split(',')]
        logger.info(f"Collecting from providers: {providers}")
    else:
        logger.info("Collecting from all providers: aws, gcp, azure")

    # Run aggregation
    try:
        stats = aggregator.aggregate_and_store(
            start_date=start_date,
            end_date=end_date,
            providers=providers
        )

        # Print summary
        logger.info("=" * 60)
        logger.info("Aggregation Summary")
        logger.info("=" * 60)
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Total records: {stats['total_records']}")
        logger.info(f"Saved records: {stats['saved_records']}")
        logger.info(f"Providers succeeded: {stats['providers_succeeded']}")
        logger.info(f"Providers failed: {stats['providers_failed']}")
        logger.info("")

        # Print cost breakdown
        for provider in ['aws', 'gcp', 'azure']:
            cost_key = f'{provider}_cost_usd'
            records_key = f'{provider}_records'
            if cost_key in stats:
                logger.info(
                    f"{provider.upper()}: ${stats[cost_key]:.2f} USD "
                    f"({stats[records_key]} records)"
                )

        logger.info("=" * 60)
        logger.info("Aggregation completed successfully")

    except Exception as e:
        logger.error(f"Aggregation failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        db_manager.close()


if __name__ == '__main__':
    main()
