#!/usr/bin/env python3
"""
build_dashboard.py
Fetches running activities from Intervals.icu and renders:
1. An ANSI-colored ASCII dashboard to run.txt (for CLI access)
2. A JSON metrics file to metrics.json (for web dashboard)

Usage:
    INTERVALS_API_KEY=your_key python build_dashboard.py
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ─── ANSI color codes ───────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[34m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"  # Overage color
WHITE   = "\033[97m"
DIM     = "\033[2m"

# ─── Config ───────────────────────────────────────────────────────────
API_URL    = "https://intervals.icu/api/v1/athlete/i694449/activities?oldest=2000-01-01"
USERNAME   = "API_KEY"
BAR_MAX    = 15
BAR_FULL   = "█"
BAR_EMPTY  = "░"
GOAL_MILES = 100.0   # Monthly mileage goal

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

RUN_TYPES: set[str] = {
    "run", "treadmill", "indoorrunning", "indoor_running",
    "trailrun", "trail_run", "trackrun", "track_run",
    "virtualrun", "virtual_run", "ultrarun", "ultra_run",
    "obstaclerun", "running",
}


def is_run(activity_type: str) -> bool:
    normalised = activity_type.lower().replace("_", "").replace(" ", "")
    return normalised in RUN_TYPES or "run" in normalised


def fetch_activities(api_key: str) -> list:
    try:
        resp = requests.get(API_URL, auth=(USERNAME, api_key), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"HTTP error fetching activities: status {status}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException:
        print("Network error fetching activities. Check connectivity.", file=sys.stderr)
        sys.exit(1)


def meters_to_miles(meters: float) -> float:
    return meters / 1609.344


def parse_date(date_str: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    raise ValueError("Unrecognised date format in API response")


def compute_metrics(runs: list) -> dict:
    now         = datetime.now(timezone.utc).replace(tzinfo=None)
    year_start  = datetime(now.year, 1, 1)
    week_ago    = now - timedelta(days=7)

    all_time_miles  = 0.0
    ytd_miles       = 0.0
    trailing7_miles = 0.0
    monthly = defaultdict(float)

    for run in runs:
        raw_dist = run.get("distance") or 0.0
        miles    = meters_to_miles(raw_dist)
        date_str = run.get("start_date_local") or run.get("start_date") or ""
        try:
            dt = parse_date(date_str)
        except ValueError:
            continue

        all_time_miles += miles

        if dt >= year_start:
            ytd_miles += miles
            monthly[dt.month] += miles

        if dt >= week_ago:
            trailing7_miles += miles

    return {
        "all_time":      round(all_time_miles, 1),
        "ytd":           round(ytd_miles, 1),
        "trailing7":     round(trailing7_miles, 1),
        "monthly":       {m: round(monthly.get(m, 0.0), 1) for m in range(1, 13)},
        "year":          now.year,
        "current_month": now.month,
        "generated":     now.strftime("%Y-%m-%d %H:%M UTC"),
    }


def strip_ansi(text: str) -> str:
    """Strip ANSI codes for calculating accurate visible padding length."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def render_dashboard(metrics: dict) -> str:
    W = 58  # Inner width
    lines = []

    def border_top():
        return f"{BLUE}┌{'─' * W}┐{RESET}"

    def border_mid():
        return f"{BLUE}├{'─' * W}┤{RESET}"

    def border_bot():
        return f"{BLUE}└{'─' * W}┘{RESET}"

    def border_row(text: str):
        vis_len = len(strip_ansi(text))
        pad = " " * max(0, W - vis_len - 2)
        return f"{BLUE}│{RESET} {text}{pad} {BLUE}│{RESET}"

    def plain_row(text: str, width: int = W):
        return f"{BLUE}│{RESET} {text:<{width - 2}} {BLUE}│{RESET}"

    # ── Header ──────────────────────────────────────────────────────────
    lines.append(border_top())
    lines.append(plain_row(f"{BOLD}{BLUE}RUNNING DASHBOARD{RESET}"))
    lines.append(plain_row(f"{DIM}Updated: {metrics['generated']}{RESET}"))
    lines.append(plain_row(""))

    # ── Summary stats ────────────────────────────────────────────────────────
    lines.append(border_mid())
    lines.append(plain_row(f"{BOLD}{WHITE}SUMMARY STATS{RESET}"))
    lines.append(border_mid())

    stats = [
        ("All-Time Mileage", f"{metrics['all_time']:,.1f} mi"),
        ("Year-to-Date",     f"{metrics['ytd']:,.1f} mi  ({metrics['year']})"),
        ("Trailing 7 Days",  f"{metrics['trailing7']:,.1f} mi"),
    ]
    for label, value in stats:
        dots = "." * max(1, W - len(label) - len(value) - 6)
        row  = f"{CYAN}{label}{RESET}{dots}{BOLD}{WHITE}{value}{RESET}"
        lines.append(border_row(row))

    # ── Monthly bar chart ─────────────────────────────────────────────────────
    lines.append(border_mid())
    lines.append(plain_row(f"{BOLD}{WHITE}{metrics['year']} MONTHLY BREAKDOWN{RESET}"))
    lines.append(border_mid())

    monthly       = metrics["monthly"]
    current_month = metrics.get("current_month", 12)
    max_miles     = max(list(monthly.values()) + [GOAL_MILES])

    # Show only up to current month (filters future 0.0 mi months)
    for month_num in range(1, current_month + 1):
        miles = monthly.get(month_num, 0.0)

        if miles >= GOAL_MILES:
            goal_blocks  = round((GOAL_MILES / max_miles) * BAR_MAX)
            over_miles   = miles - GOAL_MILES
            over_blocks  = round((over_miles / max_miles) * BAR_MAX)
            empty_blocks = max(0, BAR_MAX - goal_blocks - over_blocks)

            bar_str = (
                f"{GREEN}{BAR_FULL * goal_blocks}"
                f"{YELLOW}{BAR_FULL * over_blocks}"
                f"{DIM}{BAR_EMPTY * empty_blocks}{RESET}"
            )
            
            if over_miles > 0.05:
                miles_str = f"{GREEN}{miles:5.1f} mi{RESET} {YELLOW}(+{over_miles:.1f}){RESET}"
            else:
                miles_str = f"{GREEN}{miles:5.1f} mi{RESET} {GREEN}★{RESET}"
        else:
            filled = round((miles / max_miles) * BAR_MAX)
            empty  = BAR_MAX - filled
            bar_str = f"{CYAN}{BAR_FULL * filled}{RESET}{DIM}{BAR_EMPTY * empty}{RESET}"
            miles_str = f"{BOLD}{WHITE}{miles:5.1f} mi{RESET}"

        row = f"{CYAN}{MONTH_NAMES[month_num - 1]}{RESET} {bar_str} {miles_str}"
        lines.append(border_row(row))

    lines.append(border_bot())
    return "\n".join(lines)


def main():
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        print("Error: INTERVALS_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    activities = fetch_activities(api_key)
    runs       = [a for a in activities if is_run(a.get("type", ""))]
    metrics    = compute_metrics(runs)
    dashboard  = render_dashboard(metrics)

    with open("run.txt", "w") as f:
        f.write(dashboard + "\n")
    print("✓ Written run.txt", file=sys.stderr)

    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
    print("✓ Written metrics.json", file=sys.stderr)


if __name__ == "__main__":
    main()