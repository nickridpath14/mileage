#!/usr/bin/env python3
"""
build_dashboard.py
Fetches running activities from Intervals.icu and renders an ANSI-colored
ASCII dashboard to stdout. Pipe the output to run.txt for static hosting.

Usage:
    INTERVALS_API_KEY=your_key python build_dashboard.py > run.txt
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from collections import defaultdict

# ─── ANSI color codes ─────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
BLUE    = "\033[34m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
WHITE   = "\033[97m"
DIM     = "\033[2m"

# ─── Config ───────────────────────────────────────────────────────────────────
API_URL   = "https://intervals.icu/api/v1/athlete/i694449/activities?oldest=2000-01-01"
USERNAME  = "API_KEY"
BAR_MAX   = 15
BAR_FULL  = "█"
BAR_EMPTY = "░"

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# All activity-type strings that Garmin, Strava, Wahoo, and other platforms
# send to Intervals.icu that represent some form of running.
# Types are matched case-insensitively so minor capitalisation differences
# (e.g. "trail_run" vs "TrailRun") are handled automatically.
RUN_TYPES: set[str] = {
    # Standard outdoor run
    "run",
    # Treadmill / indoor
    "treadmill",
    "indoorrunning",
    "indoor_running",
    # Trail
    "trailrun",
    "trail_run",
    # Track
    "trackrun",
    "track_run",
    # Virtual / Zwift run
    "virtualrun",
    "virtual_run",
    # Garmin ultra-run category
    "ultrarun",
    "ultra_run",
    # Garmin obstacle / mud run
    "obstaclerun",
    # Strava "Race" subtype that maps to running
    "running",
}


def is_run(activity_type: str) -> bool:
    """Return True if the activity type is any form of running.

    Normalises the type string by lowercasing and stripping underscores/spaces
    so that variants like 'TrailRun', 'trail_run', and 'trail run' all match.
    Falls back to a substring check ('run' in type) to catch any future or
    platform-specific type strings not yet in RUN_TYPES.
    """
    normalised = activity_type.lower().replace("_", "").replace(" ", "")
    return normalised in RUN_TYPES or "run" in normalised


def fetch_activities(api_key: str) -> list:

    try:
        resp = requests.get(API_URL, auth=(USERNAME, api_key), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        # Log only the status code — never the response body, which may contain
        # private athlete data that would surface in public GitHub Actions logs.
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"HTTP error fetching activities: status {status}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException:
        # Suppress the full exception string; it can include URLs with embedded
        # credentials or server error messages.
        print("Network error fetching activities. Check connectivity.", file=sys.stderr)
        sys.exit(1)


def meters_to_miles(meters: float) -> float:
    return meters / 1609.344


def parse_date(date_str: str) -> datetime:
    """Parse ISO 8601 date string (first 19 chars)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    # Do NOT include date_str in the message — it is a raw API field
    raise ValueError("Unrecognised date format in API response")


def compute_metrics(runs: list) -> dict:
    now         = datetime.now()
    year_start  = datetime(now.year, 1, 1)
    week_ago    = now - timedelta(days=7)

    all_time_miles  = 0.0
    ytd_miles       = 0.0
    trailing7_miles = 0.0
    monthly = defaultdict(float)  # month (1-12) → miles

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
        "all_time":  all_time_miles,
        "ytd":       ytd_miles,
        "trailing7": trailing7_miles,
        "monthly":   dict(monthly),
        "year":      now.year,
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
    }


# ─── Rendering helpers ────────────────────────────────────────────────────────

def bar(miles: float, max_miles: float) -> str:
    """Render a proportional block bar."""
    if max_miles == 0:
        filled = 0
    else:
        filled = round((miles / max_miles) * BAR_MAX)
    empty = BAR_MAX - filled
    return f"{GREEN}{BAR_FULL * filled}{RESET}{DIM}{BAR_EMPTY * empty}{RESET}"


def render_dashboard(metrics: dict) -> str:
    W = 58  # inner width (between the │ borders)
    lines = []

    def border_top():
        return f"{BLUE}┌{'─' * W}┐{RESET}"

    def border_mid():
        return f"{BLUE}├{'─' * W}┤{RESET}"

    def border_bot():
        return f"{BLUE}└{'─' * W}┘{RESET}"

    def border_row(text: str):
        """Row where text already contains ANSI codes — right border only."""
        return f"{BLUE}│{RESET} {text} {BLUE}│{RESET}"

    def plain_row(text: str, width: int = W):
        """Row with plain text, padded to width, then bordered."""
        return f"{BLUE}│{RESET} {text:<{width - 2}} {BLUE}│{RESET}"

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(border_top())
    lines.append(plain_row(f"{BOLD}{BLUE}🏃  RUNNING DASHBOARD{RESET}"))
    lines.append(plain_row(f"{DIM}Updated: {metrics['generated']}{RESET}"))
    lines.append(plain_row(""))

    # ── Summary stats ─────────────────────────────────────────────────────────
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

    monthly   = metrics["monthly"]
    max_miles = max(monthly.values(), default=1.0)

    for month_num in range(1, 13):
        miles     = monthly.get(month_num, 0.0)
        month_bar = bar(miles, max_miles)
        miles_str = f"{miles:5.1f} mi"
        row = (
            f"{CYAN}{MONTH_NAMES[month_num - 1]}{RESET} "
            f"{month_bar} "
            f"{BOLD}{WHITE}{miles_str}{RESET}"
        )
        lines.append(border_row(row))

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append(border_mid())
    lines.append(plain_row(f"{DIM}Data: intervals.icu  |  Rendered by build_dashboard.py{RESET}"))
    lines.append(border_bot())

    return "\n".join(lines)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    # Retrieve the API key exclusively from the environment — never hardcode it.
    # The script exits here before any network call if the variable is absent,
    # ensuring no partial or anonymous request is made.
    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        print("Error: INTERVALS_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    activities = fetch_activities(api_key)
    runs       = [a for a in activities if is_run(a.get("type", ""))]
    metrics    = compute_metrics(runs)
    dashboard  = render_dashboard(metrics)

    print(dashboard)


if __name__ == "__main__":
    main()
