"""
Date utility functions for calculating date ranges
"""
import datetime
from typing import Tuple


def get_date_range(
    backfill: bool = False,
    lookback_days: int = 2,
    backfill_days: int = 90,
    start_date: datetime.date = None,
    end_date: datetime.date = None
) -> Tuple[datetime.date, datetime.date]:
    """
    Calculate the date range for fetching cloud costs

    Args:
        backfill: If True, fetch historical data
        lookback_days: Number of days to look back from today (default: 2 for T-2)
        backfill_days: Number of days to backfill (default: 90)
        start_date: Optional custom start date
        end_date: Optional custom end date

    Returns:
        Tuple of (start_date, end_date)

    Examples:
        # Daily run (T-2 day only)
        >>> get_date_range()
        (date(2025, 11, 8), date(2025, 11, 8))

        # Backfill mode (past 90 days)
        >>> get_date_range(backfill=True)
        (date(2025, 8, 10), date(2025, 11, 8))

        # Custom date range
        >>> get_date_range(start_date=date(2025, 10, 1), end_date=date(2025, 10, 31))
        (date(2025, 10, 1), date(2025, 10, 31))
    """
    today = datetime.date.today()

    # If custom dates are provided, use them
    if start_date and end_date:
        return start_date, end_date

    # Calculate end date (T-2 by default)
    if end_date is None:
        end_date = today - datetime.timedelta(days=1)

    # Calculate start date
    if start_date is None:
        if backfill:
            # Backfill mode: go back N days from end_date
            start_date = end_date - datetime.timedelta(days=backfill_days)
        else:
            # Daily mode: same as end_date (single day)
            start_date = end_date - datetime.timedelta(days=3)

    return start_date, end_date


def get_t_minus_n_date(days: int = 2) -> datetime.date:
    """
    Get the date N days ago (T-N)

    Args:
        days: Number of days to go back (default: 2)

    Returns:
        Date N days ago
    """
    return datetime.date.today() - datetime.timedelta(days=days)


def format_date_for_api(date: datetime.date) -> str:
    """
    Format date for cloud provider APIs (YYYY-MM-DD)

    Args:
        date: Date to format

    Returns:
        Formatted date string
    """
    return date.strftime('%Y-%m-%d')


def parse_date_string(date_str: str) -> datetime.date:
    """
    Parse date string in YYYY-MM-DD format

    Args:
        date_str: Date string

    Returns:
        Parsed date object

    Raises:
        ValueError: If date string is invalid
    """
    return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()


def get_date_list(start_date: datetime.date, end_date: datetime.date) -> list[datetime.date]:
    """
    Get list of all dates between start and end (inclusive)

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        List of dates
    """
    date_list = []
    current_date = start_date

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += datetime.timedelta(days=1)

    return date_list
