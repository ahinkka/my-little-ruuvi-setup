#!/usr/bin/env python3
"""
Extract Historical Daily Summaries

Extracts temperature and humidity data from SQLite database files, aggregates
to daily summaries (min, max, median), and outputs TSV to stdout. Supports
multiple database formats:

  - legacy_summary: Tables like `summary_temperature_3600` with `starts_at`,
    `sensor`, `median_value` columns (Unix timestamps)

  - individual_value: Tables like `measurement_temperature` with `recorded_at`,
    `sensor`, `value` columns (ISO timestamps, raw measurements)

  - aggregated: Tables like `measurement_temperature` with `recorded_at`,
    `sensor`, `median` columns (ISO timestamps, pre-aggregated)

  - summary_collector: Tables like `hourly_temperature`, `daily_temperature`
    with `period_start_at`, `sensor`, `minimum`, `maximum`, `median`, `mean`
    columns (output format of measurement_summary_collector.py)

The script auto-detects the schema type for each database. When the same
(day, sensor, measurement_type) combination appears in multiple databases,
later databases in the argument list take precedence.

Usage:
    python extract_historical_daily.py db1.db db2.db ... > history_daily_summary.tsv

Example:
    python3 extract_historical_daily.py \\
        a.db \\
        b.db \\
        measurement-summaries.db \\
        > history_daily_summary.tsv

Output format (TSV to stdout):
    timestamp<TAB>sensor<TAB>measurement_type<TAB>min<TAB>max<TAB>median

Where timestamp is Unix epoch (seconds) for start of day in UTC.
Progress and summary information is written to stderr.
"""

import argparse
import sqlite3
import sys
import statistics
from datetime import datetime
from collections import defaultdict
from pathlib import Path


MEASUREMENT_TYPES = ['temperature', 'humidity']


def get_tables(conn):
    """Get list of tables in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_columns(conn, table_name):
    """Get column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def detect_schema_type(conn):
    """Detect which schema type this database uses."""
    tables = get_tables(conn)

    # Check for summary_collector format (measurement_summary_collector.py output)
    if 'hourly_temperature' in tables or 'daily_temperature' in tables:
        return 'summary_collector'

    if 'summary_temperature_3600' in tables:
        return 'legacy_summary'

    if 'measurement_temperature' in tables:
        columns = get_table_columns(conn, 'measurement_temperature')
        if 'value' in columns:
            return 'individual_value'
        elif 'median' in columns:
            return 'aggregated'

    return 'unknown'


def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime."""
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        return datetime.strptime(ts_str[:19], '%Y-%m-%dT%H:%M:%S')


def hour_key(dt):
    """Get hour key (truncated to hour) from datetime."""
    return dt.replace(minute=0, second=0, microsecond=0)


def day_start_unix(dt):
    """Get Unix timestamp for start of day in UTC from datetime."""
    # Convert to UTC day boundary
    unix_ts = int(dt.timestamp())
    DAY_SECS = 86400
    return (unix_ts // DAY_SECS) * DAY_SECS


def day_start_unix_from_ts(unix_ts):
    """Get Unix timestamp for start of day in UTC from Unix timestamp."""
    DAY_SECS = 86400
    return (unix_ts // DAY_SECS) * DAY_SECS


def extract_legacy_summary(conn, measurement_type):
    """Extract hourly data from legacy summary tables."""
    table_name = f'summary_{measurement_type}_3600'

    tables = get_tables(conn)
    if table_name not in tables:
        return []

    query = f"""
        SELECT starts_at, sensor, median_value
        FROM {table_name}
        WHERE median_value IS NOT NULL
        ORDER BY starts_at, sensor
    """

    cursor = conn.execute(query)
    rows = []
    for unix_ts, sensor, value in cursor.fetchall():
        dt = datetime.fromtimestamp(unix_ts)
        rows.append((dt, sensor, value))
    return rows


def extract_individual_value(conn, measurement_type):
    """Extract and aggregate raw measurements to hourly."""
    table_name = f'measurement_{measurement_type}'

    tables = get_tables(conn)
    if table_name not in tables:
        return []

    query = f"""
        SELECT recorded_at, sensor, value
        FROM {table_name}
        WHERE value IS NOT NULL
        ORDER BY recorded_at, sensor
    """

    cursor = conn.execute(query)

    # Group by sensor and hour
    sensor_hourly = defaultdict(lambda: defaultdict(list))
    for ts_str, sensor, value in cursor.fetchall():
        dt = parse_timestamp(ts_str)
        hour = hour_key(dt)
        sensor_hourly[sensor][hour].append(value)

    # Compute median for each hour
    rows = []
    for sensor in sorted(sensor_hourly.keys()):
        hourly_data = sensor_hourly[sensor]
        for hour in sorted(hourly_data.keys()):
            values = hourly_data[hour]
            median_val = statistics.median(values)
            rows.append((hour, sensor, median_val))

    return rows


def extract_aggregated(conn, measurement_type):
    """Extract from pre-aggregated tables."""
    table_name = f'measurement_{measurement_type}'

    tables = get_tables(conn)
    if table_name not in tables:
        return []

    columns = get_table_columns(conn, table_name)
    if 'median' not in columns:
        return []

    query = f"""
        SELECT recorded_at, sensor, median
        FROM {table_name}
        WHERE median IS NOT NULL
        ORDER BY recorded_at, sensor
    """

    cursor = conn.execute(query)

    # Group by sensor and hour (may have sub-hourly granularity)
    hourly_data = defaultdict(list)
    for ts_str, sensor, median_val in cursor.fetchall():
        dt = parse_timestamp(ts_str)
        hour = hour_key(dt)
        hourly_data[(hour, sensor)].append(median_val)

    # Compute median for each hour
    rows = []
    for (hour, sensor), values in sorted(hourly_data.items()):
        if len(values) == 1:
            val = values[0]
        else:
            val = statistics.median(values)
        rows.append((hour, sensor, val))

    return rows


def extract_summary_collector(conn, measurement_type):
    """Extract from summary_collector format (hourly/daily tables)."""
    tables = get_tables(conn)

    # Prefer hourly data for finer granularity, fall back to daily
    hourly_table = f'hourly_{measurement_type}'
    daily_table = f'daily_{measurement_type}'

    if hourly_table in tables:
        table_name = hourly_table
    elif daily_table in tables:
        table_name = daily_table
    else:
        return []

    query = f"""
        SELECT period_start_at, sensor, median
        FROM {table_name}
        WHERE median IS NOT NULL
        ORDER BY period_start_at, sensor
    """

    cursor = conn.execute(query)
    rows = []
    for unix_ts, sensor, median_val in cursor.fetchall():
        dt = datetime.fromtimestamp(unix_ts)
        rows.append((dt, sensor, median_val))
    return rows


def extract_hourly_data(db_path, measurement_type):
    """Extract hourly data from a database, auto-detecting schema."""
    try:
        conn = sqlite3.connect(db_path)
        schema_type = detect_schema_type(conn)

        if schema_type == 'legacy_summary':
            rows = extract_legacy_summary(conn, measurement_type)
        elif schema_type == 'individual_value':
            rows = extract_individual_value(conn, measurement_type)
        elif schema_type == 'aggregated':
            rows = extract_aggregated(conn, measurement_type)
        elif schema_type == 'summary_collector':
            rows = extract_summary_collector(conn, measurement_type)
        else:
            rows = []

        conn.close()
        return schema_type, rows
    except Exception as e:
        print(f"Error extracting from {db_path}: {e}", file=sys.stderr)
        return 'error', []


def aggregate_to_daily(hourly_rows):
    """Aggregate hourly values to daily min/max/median."""
    # Group by (day_unix, sensor)
    daily_data = defaultdict(list)

    for dt, sensor, value in hourly_rows:
        day_unix = day_start_unix(dt)
        daily_data[(day_unix, sensor)].append(value)

    # Compute daily statistics
    daily_stats = {}
    for (day_unix, sensor), values in daily_data.items():
        daily_stats[(day_unix, sensor)] = {
            'min': round(min(values), 2),
            'max': round(max(values), 2),
            'median': round(statistics.median(values), 2),
        }

    return daily_stats


def main():
    parser = argparse.ArgumentParser(
        description='Extract daily summaries from measurement databases',
        epilog='Output is written to stdout as TSV. Progress info goes to stderr.'
    )
    parser.add_argument(
        'databases',
        nargs='+',
        metavar='DATABASE',
        help='SQLite database files to process (later files take precedence for duplicates)'
    )

    args = parser.parse_args()

    # Collect all hourly data per measurement type
    # Key: (day_unix, sensor, measurement_type) -> {min, max, median}
    all_daily_data = {}

    for measurement_type in MEASUREMENT_TYPES:
        print(f"Processing {measurement_type}...", file=sys.stderr)

        # Process databases in order (later overwrites earlier)
        for db_path in args.databases:
            if not Path(db_path).exists():
                print(f"  Skipping {db_path} (not found)", file=sys.stderr)
                continue

            print(f"  Extracting from {db_path}...", file=sys.stderr)
            schema_type, hourly_rows = extract_hourly_data(db_path, measurement_type)

            if not hourly_rows:
                print(f"    No {measurement_type} data found", file=sys.stderr)
                continue

            print(f"    Schema: {schema_type}, found {len(hourly_rows):,} rows", file=sys.stderr)

            # Aggregate to daily
            daily_stats = aggregate_to_daily(hourly_rows)
            print(f"    Aggregated to {len(daily_stats):,} daily rows", file=sys.stderr)

            # Merge into all_daily_data (later databases overwrite)
            for (day_unix, sensor), stats in daily_stats.items():
                key = (day_unix, sensor, measurement_type)
                all_daily_data[key] = stats

    # Output TSV to stdout
    print("# Historical daily summaries - timestamps are Unix epochs (start of day UTC)", file=sys.stdout)
    print("timestamp\tsensor\tmeasurement_type\tmin\tmax\tmedian", file=sys.stdout)

    # Sort by timestamp, sensor, measurement_type
    for key in sorted(all_daily_data.keys()):
        day_unix, sensor, measurement_type = key
        stats = all_daily_data[key]
        print(f"{day_unix}\t{sensor}\t{measurement_type}\t{stats['min']}\t{stats['max']}\t{stats['median']}", file=sys.stdout)

    # Summary
    total_rows = len(all_daily_data)
    sensors = set(k[1] for k in all_daily_data.keys())
    min_ts = min(k[0] for k in all_daily_data.keys()) if all_daily_data else 0
    max_ts = max(k[0] for k in all_daily_data.keys()) if all_daily_data else 0

    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total daily rows: {total_rows:,}", file=sys.stderr)
    print(f"  Sensors: {', '.join(sorted(sensors))}", file=sys.stderr)
    if min_ts and max_ts:
        print(f"  Date range: {datetime.fromtimestamp(min_ts).date()} to {datetime.fromtimestamp(max_ts).date()}", file=sys.stderr)


if __name__ == '__main__':
    main()
