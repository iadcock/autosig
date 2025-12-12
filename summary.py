"""
Daily trade summary module.
Generates end-of-day summaries at market close using NYSE calendar.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

logger = logging.getLogger(__name__)

NY_TZ = ZoneInfo("America/New_York")
SUMMARY_BUFFER_MINUTES = 5


def get_nyse_calendar():
    """Get the NYSE market calendar."""
    return mcal.get_calendar("NYSE")


def is_trading_day(date_obj: datetime.date) -> bool:
    """Check if a given date is a trading day."""
    calendar = get_nyse_calendar()
    schedule = calendar.schedule(
        start_date=date_obj.isoformat(),
        end_date=date_obj.isoformat()
    )
    return len(schedule) > 0


def get_market_close_time(date_obj: datetime.date) -> Optional[datetime]:
    """
    Get the market close time for a specific date.
    Returns timezone-aware datetime in America/New_York.
    Returns None if not a trading day.
    """
    calendar = get_nyse_calendar()
    schedule = calendar.schedule(
        start_date=date_obj.isoformat(),
        end_date=date_obj.isoformat()
    )
    
    if len(schedule) == 0:
        return None
    
    market_close_utc = schedule.iloc[0]['market_close']
    market_close_ny = market_close_utc.astimezone(NY_TZ)
    
    return market_close_ny


def get_today_market_close_run_time(tz: str = "America/New_York") -> Optional[datetime]:
    """
    Get the summary run time for today (market close + 5 minutes).
    Returns None if today is not a trading day.
    
    Args:
        tz: Timezone string (default: America/New_York)
    
    Returns:
        datetime: The time to run the summary (close + 5 min), or None if not trading day
    """
    tz_info = ZoneInfo(tz)
    now = datetime.now(tz_info)
    today = now.date()
    
    market_close = get_market_close_time(today)
    
    if market_close is None:
        logger.debug(f"{today} is not a trading day")
        return None
    
    run_time = market_close + timedelta(minutes=SUMMARY_BUFFER_MINUTES)
    
    logger.debug(f"Market close: {market_close}, Summary run time: {run_time}")
    
    return run_time


def get_next_trading_day(from_date: datetime.date) -> Optional[datetime.date]:
    """Get the next trading day after the given date."""
    calendar = get_nyse_calendar()
    
    search_start = from_date + timedelta(days=1)
    search_end = from_date + timedelta(days=10)
    
    schedule = calendar.schedule(
        start_date=search_start.isoformat(),
        end_date=search_end.isoformat()
    )
    
    if len(schedule) > 0:
        return schedule.index[0].date()
    
    return None


def get_next_summary_run_time(tz: str = "America/New_York") -> Optional[datetime]:
    """
    Get the next summary run time (today if not yet run, else next trading day).
    Returns timezone-aware datetime.
    """
    tz_info = ZoneInfo(tz)
    now = datetime.now(tz_info)
    today = now.date()
    
    today_run_time = get_today_market_close_run_time(tz)
    
    if today_run_time is not None and now < today_run_time:
        return today_run_time
    
    next_day = get_next_trading_day(today)
    if next_day:
        next_close = get_market_close_time(next_day)
        if next_close:
            return next_close + timedelta(minutes=SUMMARY_BUFFER_MINUTES)
    
    return None


def generate_daily_summary(trading_date: datetime.date, signals_log_file: str) -> str:
    """
    Generate a daily summary for the given trading date.
    
    Args:
        trading_date: The trading date to summarize (America/New_York date)
        signals_log_file: Path to the parsed_signals.csv file
    
    Returns:
        str: The summary text
    """
    import csv
    
    summary_lines = []
    summary_lines.append("=" * 60)
    summary_lines.append(f"DAILY TRADE SUMMARY - {trading_date.isoformat()}")
    summary_lines.append("=" * 60)
    summary_lines.append("")
    
    market_close = get_market_close_time(trading_date)
    if market_close:
        close_time_str = market_close.strftime("%I:%M %p %Z")
        summary_lines.append(f"Market Close: {close_time_str}")
        
        if market_close.hour < 16:
            summary_lines.append("(Early Close Day)")
    summary_lines.append("")
    
    trades = []
    
    if os.path.exists(signals_log_file):
        try:
            with open(signals_log_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ts = datetime.fromisoformat(row['timestamp'])
                        ts_ny = ts.astimezone(NY_TZ) if ts.tzinfo else ts.replace(tzinfo=NY_TZ)
                        
                        if ts_ny.date() == trading_date:
                            trades.append(row)
                    except (ValueError, KeyError):
                        continue
        except Exception as e:
            logger.error(f"Error reading signals log: {e}")
    
    summary_lines.append(f"Total Signals Processed: {len(trades)}")
    summary_lines.append("-" * 40)
    summary_lines.append("")
    
    if trades:
        by_status = {}
        by_ticker = {}
        
        for trade in trades:
            status = trade.get('status', 'UNKNOWN')
            ticker = trade.get('ticker', 'UNKNOWN')
            
            by_status[status] = by_status.get(status, 0) + 1
            by_ticker[ticker] = by_ticker.get(ticker, 0) + 1
        
        summary_lines.append("By Status:")
        for status, count in sorted(by_status.items()):
            summary_lines.append(f"  {status}: {count}")
        summary_lines.append("")
        
        summary_lines.append("By Ticker:")
        for ticker, count in sorted(by_ticker.items()):
            summary_lines.append(f"  {ticker}: {count}")
        summary_lines.append("")
        
        summary_lines.append("Trade Details:")
        summary_lines.append("-" * 40)
        
        for i, trade in enumerate(trades, 1):
            ts = trade.get('timestamp', '')[:19]
            ticker = trade.get('ticker', '')
            strategy = trade.get('strategy', '')
            status = trade.get('status', '')
            legs = trade.get('legs', '')
            
            summary_lines.append(f"{i}. [{ts}] {ticker} - {strategy}")
            summary_lines.append(f"   Status: {status}")
            if legs:
                summary_lines.append(f"   Legs: {legs}")
            summary_lines.append("")
    else:
        summary_lines.append("No trades recorded for this day.")
        summary_lines.append("")
    
    summary_lines.append("=" * 60)
    summary_lines.append(f"Generated at: {datetime.now(NY_TZ).isoformat()}")
    summary_lines.append("=" * 60)
    
    return "\n".join(summary_lines)


def write_daily_summary(trading_date: datetime.date, signals_log_file: str, output_dir: str = "logs") -> str:
    """
    Generate and write the daily summary to a file.
    
    Args:
        trading_date: The trading date to summarize
        signals_log_file: Path to the parsed_signals.csv file
        output_dir: Directory to write summary files
    
    Returns:
        str: Path to the written summary file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    summary_text = generate_daily_summary(trading_date, signals_log_file)
    
    filename = f"daily_summary_{trading_date.isoformat()}.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write(summary_text)
    
    logger.info(f"Daily summary written to: {filepath}")
    
    return filepath
