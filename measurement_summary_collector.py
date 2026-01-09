#!/usr/bin/env python3
import asyncio
import contextlib
import datetime as dt
import json
import logging
import sqlite3
import statistics
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import URLError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TABLE_PERIODS = ('hourly', 'daily')
MEASUREMENT_TYPES = ('temperature', 'humidity')
CHECK_INTERVAL_SECONDS = 30


def table_name(period, measurement_type):
    return f'{period}_{measurement_type}'


def create_sql(period, measurement_type):
    return f'''CREATE TABLE IF NOT EXISTS {table_name(period, measurement_type)} (
  period_start_at INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  minimum REAL,
  maximum REAL,
  median REAL,
  mean REAL,
  CONSTRAINT period_start_at_sensor_pk PRIMARY KEY (period_start_at, sensor)
) WITHOUT ROWID'''


def create_tables(conn):
    for period in TABLE_PERIODS:
        for measurement_type in MEASUREMENT_TYPES:
            conn.execute(create_sql(period, measurement_type))
    conn.commit()


def insert_summary(conn, table, period_start_at, sensor, stats):
    conn.execute(f'''
        INSERT OR REPLACE INTO {table}
          (period_start_at, sensor, minimum, maximum, median, mean)
        VALUES
          (?, ?, ?, ?, ?, ?)
    ''', (
        period_start_at,
        sensor,
        stats['minimum'],
        stats['maximum'],
        stats['median'],
        stats['mean']
    ))


def fetch_measurements(hostname, port, start_timestamp, end_timestamp):
    url = f'http://{hostname}:{port}/measurements.json?start={start_timestamp}&end={end_timestamp}'
    try:
        with urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except (URLError, json.JSONDecodeError, TimeoutError, ConnectionRefusedError, OSError) as e:
        logger.warning(f'Failed to fetch measurements from {hostname}:{port}: {e}')
        return None


def calculate_statistics(values):
    if not values:
        return {
            'minimum': None,
            'maximum': None,
            'median': None,
            'mean': None
        }

    return {
        'minimum': min(values),
        'maximum': max(values),
        'median': statistics.median(values),
        'mean': statistics.mean(values)
    }


def get_previous_hour_range():
    now = datetime.now()
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    prev_hour_end = current_hour_start
    prev_hour_start = prev_hour_end - timedelta(hours=1)
    return int(prev_hour_start.timestamp()), int(prev_hour_end.timestamp())


def get_previous_day_range():
    now = datetime.now()
    current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_day_end = current_day_start
    prev_day_start = prev_day_end - timedelta(days=1)
    return int(prev_day_start.timestamp()), int(prev_day_end.timestamp())


def collect_hourly_summaries(conn, hostname, port):
    start_ts, end_ts = get_previous_hour_range()
    period_start_at = start_ts

    data = fetch_measurements(hostname, port, start_ts, end_ts)
    if data is None:
        logger.warning('Skipping hourly summary collection - measurement_buffer unavailable')
        return

    for sensor_id, measurements in data.items():
        temp_values = [m['temperature'] for m in measurements if m.get('temperature') is not None]
        temp_stats = calculate_statistics(temp_values)
        insert_summary(conn, 'hourly_temperature', period_start_at, sensor_id, temp_stats)

        humidity_values = [m['humidity'] for m in measurements if m.get('humidity') is not None]
        humidity_stats = calculate_statistics(humidity_values)
        insert_summary(conn, 'hourly_humidity', period_start_at, sensor_id, humidity_stats)

    conn.commit()
    logger.info(f'Collected hourly summaries for {len(data)} sensors (period starting {datetime.fromtimestamp(start_ts)})')


def collect_daily_summaries(conn, hostname, port):
    start_ts, end_ts = get_previous_day_range()
    period_start_at = start_ts

    data = fetch_measurements(hostname, port, start_ts, end_ts)
    if data is None:
        logger.warning('Skipping daily summary collection - measurement_buffer unavailable')
        return

    for sensor_id, measurements in data.items():
        temp_values = [m['temperature'] for m in measurements if m.get('temperature') is not None]
        temp_stats = calculate_statistics(temp_values)
        insert_summary(conn, 'daily_temperature', period_start_at, sensor_id, temp_stats)

        humidity_values = [m['humidity'] for m in measurements if m.get('humidity') is not None]
        humidity_stats = calculate_statistics(humidity_values)
        insert_summary(conn, 'daily_humidity', period_start_at, sensor_id, humidity_stats)

    conn.commit()
    logger.info(f'Collected daily summaries for {len(data)} sensors (period starting {datetime.fromtimestamp(start_ts)})')


@dataclass
class SchedulerState:
    last_processed_hour: int
    last_processed_day: int
    last_processed_year: int


async def main(hostname, port, database):
    now = datetime.now()
    state = SchedulerState(
        last_processed_hour=now.hour,
        last_processed_day=now.timetuple().tm_yday,
        last_processed_year=now.year
    )

    logger.info(f'Starting measurement summary collector')
    logger.info(f'Data source: {hostname}:{port}')
    logger.info(f'Database: {database}')

    with contextlib.closing(
            sqlite3.connect(database,
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        create_tables(conn)

        while True:
            try:
                now = datetime.now()
                current_hour = now.hour
                current_day = now.timetuple().tm_yday
                current_year = now.year

                if current_hour != state.last_processed_hour:
                    logger.info(f'Hour changed from {state.last_processed_hour} to {current_hour}')
                    collect_hourly_summaries(conn, hostname, port)
                    state.last_processed_hour = current_hour

                if current_day != state.last_processed_day or current_year != state.last_processed_year:
                    logger.info(f'Day changed')
                    collect_daily_summaries(conn, hostname, port)
                    state.last_processed_day = current_day
                    state.last_processed_year = current_year

                await asyncio.sleep(CHECK_INTERVAL_SECONDS)

            except Exception as e:
                logger.error(f'Unexpected error in main loop: {e}')
                traceback.print_exc()
                await asyncio.sleep(60)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog='measurement_summary_collector.py',
        description='Collect hourly and daily measurement summaries from measurement_buffer'
    )

    parser.add_argument('--hostname', default='localhost',
                        help='Host where measurement_buffer.py runs (default: localhost)')
    parser.add_argument('--port', default=22223, type=int,
                        help='HTTP port of measurement_buffer.py (default: 22223)')
    parser.add_argument('--database', default='measurement-summaries.db',
                        help='Path to SQLite database file (default: measurement-summaries.db)')
    parser.add_argument('--debug', default=False, action='store_true',
                        help='Enable debug logging')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    asyncio.run(main(args.hostname, args.port, args.database))
