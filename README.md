# Mileage Dashboard

An automated running mileage dashboard that pulls activity data from [Intervals.icu](https://intervals.icu) and publishes two dashboard interfaces:

- **Web Dashboard (`index.html`)**: A modern dark-mode React dashboard displaying summary metrics (All-Time, Year-to-Date, Trailing 7 Days) and a monthly mileage breakdown chart.
- **Terminal Dashboard (`run.txt`)**: An ANSI-formatted ASCII text dashboard suitable for CLI access and `curl`.

---

## Architecture

1. **`build_dashboard.py`**:
   - Queries the Intervals.icu API for athlete activities.
   - Filters running activities across Garmin, Strava, and other sources.
   - Calculates total mileage, YTD mileage, trailing 7-day mileage, and monthly breakdowns.
   - Outputs:
     - `run.txt` (ANSI ASCII dashboard)
     - `metrics.json` (raw metrics for frontend consumption)

2. **`index.html`**:
   - React 18 single-page application served via CDN (no build step required).
   - Polls `metrics.json` to render live stats with cache busting.

3. **GitHub Actions (`.github/workflows/update.yml`)**:
   - Runs automatically on a cron schedule (`0 */6 * * *`) and on manual dispatch.
   - Executes `python build_dashboard.py`.
   - Commits and pushes changes to `run.txt` and `metrics.json`.

---

## Setup & Local Development

### Prerequisites

- Python 3.10+
- `requests` library:
  ```bash
  pip install requests
  ```

### Generate Dashboards Locally

Set your Intervals.icu API key and run the script:

```bash
export INTERVALS_API_KEY="your_api_key_here"
python build_dashboard.py
```

### View the Web Dashboard Locally

Because browsers enforce CORS restrictions on local file fetches (`file://`), serve the directory using Python's built-in HTTP server:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000` in your browser.

---

## GitHub Actions Configuration

To automate data fetching:

1. Go to repository **Settings** &rarr; **Secrets and variables** &rarr; **Actions**.
2. Add a new repository secret named `INTERVALS_API_KEY` with your Intervals.icu API key.
3. The workflow will automatically run every 6 hours and update `run.txt` and `metrics.json`.
