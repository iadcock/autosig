"""
Fetch and parse recent Whop alerts, saving results to a file.
"""

import json
from datetime import datetime

import config
from scraper_whop import WhopScraper, fetch_alerts_from_local_file
from parser import parse_alert, parse_multiple_alerts


def fetch_and_parse_alerts(use_whop: bool = True) -> None:
    """Fetch alerts from Whop or local file and save parsed results."""
    
    print("=" * 60)
    print("FETCHING AND PARSING ALERTS")
    print("=" * 60)
    
    if use_whop and config.WHOP_ALERTS_URL and config.WHOP_SESSION:
        print("Fetching from Whop...")
        scraper = WhopScraper()
        raw_alerts = scraper.fetch_alerts()
        source = "Whop"
    else:
        print("Using local sample_alerts.txt...")
        raw_alerts = fetch_alerts_from_local_file()
        source = "Local File"
    
    if not raw_alerts:
        print("No alerts fetched!")
        return
    
    print(f"Source: {source}")
    print(f"Raw text length: {len(raw_alerts)} characters")
    print()
    
    with open("raw_alerts.txt", "w") as f:
        f.write(f"# Raw alerts fetched from {source}\n")
        f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")
        f.write(raw_alerts)
    
    print("Raw alerts saved to: raw_alerts.txt")
    
    signals = parse_multiple_alerts(raw_alerts)
    print(f"Parsed {len(signals)} valid signals")
    print()
    
    output_lines = []
    output_lines.append(f"# Parsed Signals from {source}")
    output_lines.append(f"# Timestamp: {datetime.now().isoformat()}")
    output_lines.append(f"# Total valid signals: {len(signals)}")
    output_lines.append("=" * 60)
    output_lines.append("")
    
    for i, signal in enumerate(signals, 1):
        output_lines.append(f"SIGNAL #{i}")
        output_lines.append("-" * 40)
        output_lines.append(f"Ticker: {signal.ticker}")
        output_lines.append(f"Strategy: {signal.strategy}")
        output_lines.append(f"Expiration: {signal.expiration}")
        output_lines.append(f"Position Size: {signal.size_pct * 100:.1f}%")
        output_lines.append(f"Limit: ${signal.limit_min:.2f} - ${signal.limit_max:.2f} ({signal.limit_kind})")
        
        if signal.legs:
            output_lines.append("Legs:")
            for leg in signal.legs:
                output_lines.append(f"  {leg.side} {leg.quantity} x ${leg.strike} {leg.option_type}")
        
        output_lines.append("")
        output_lines.append("Raw Alert Text:")
        for line in signal.raw_text.strip().split('\n'):
            output_lines.append(f"  | {line}")
        
        output_lines.append("")
        output_lines.append("=" * 60)
        output_lines.append("")
    
    with open("parsed_signals.txt", "w") as f:
        f.write("\n".join(output_lines))
    
    print("Parsed signals saved to: parsed_signals.txt")
    print()
    
    for i, signal in enumerate(signals, 1):
        print(f"Signal #{i}: {signal.ticker} - {signal.strategy}")
        print(f"  Expiration: {signal.expiration}")
        print(f"  Size: {signal.size_pct * 100:.1f}%")
        print(f"  Limit: ${signal.limit_min:.2f}-${signal.limit_max:.2f} {signal.limit_kind}")
        if signal.legs:
            legs_str = " / ".join([f"{l.side[0]}{l.quantity} ${l.strike}{l.option_type[0]}" for l in signal.legs])
            print(f"  Legs: {legs_str}")
        print()


if __name__ == "__main__":
    fetch_and_parse_alerts(use_whop=True)
