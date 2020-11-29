#!/usr/bin/env python3
import contextlib
import re
import sqlite3
import time
import datetime as dt
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def table_name(measurement_type, period_secs):
    return f"summary_{measurement_type}_{period_secs}"


def create_sql(measurement_type, period_secs):
    return f"""CREATE TABLE IF NOT EXISTS {table_name(measurement_type, period_secs)} (
  starts_at INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  min_value REAL,
  max_value REAL,
  median_value REAL,
  mean_value REAL,
  CONSTRAINT starts_at_sensor_pk PRIMARY KEY (starts_at, sensor)
) WITHOUT ROWID
"""


def summarize_period_containing(conn, measurement_type, period_secs, containing_epoch_secs):
    period_start = containing_epoch_secs - (containing_epoch_secs % period_secs)

    sensors = list(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM measurement'))

    for sensor in sensors:
        values = list(r[0] for r in conn.execute(f"SELECT {measurement_type} FROM measurement WHERE sensor = ? AND recorded_at >= ?", (sensor, period_start,)))

        if len(values) == 0:
            logger.debug(f'No {measurement_type} values for {sensor} starting {period_start}, period {period_secs}')
            continue

        values.sort()

        conn.execute(
            f"""
INSERT OR REPLACE INTO {table_name(measurement_type, period_secs)}
  (starts_at, sensor, min_value, max_value, median_value, mean_value)
VALUES
  (?, ?, ?, ?, ?, ?)""", (
      period_start,
      sensor,
      values[0],
      values[-1],
      values[int(len(values) / 2.0)],
      sum(values) / float(len(values))))

        conn.commit()


def summarize_single_period(conn, period_secs, epoch_secs_containing):
        for measurement_type in [
                'temperature',
                'humidity',
                'pressure',
                'battery_voltage',
                'tx_power'
        ]:
            conn.execute(create_sql(measurement_type, period_secs))
            summarize_period_containing(conn, measurement_type, period_secs, epoch_secs_containing)


def summarize_latest(args):
    with contextlib.closing(
            sqlite3.connect('measurements_backup.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        summarize_single_period(conn, 3600, int(time.time()))
        summarize_single_period(conn, 43200, int(time.time()))
        summarize_single_period(conn, 86400, int(time.time()))


def summarize_since(args):
    with contextlib.closing(
            sqlite3.connect('measurements_backup.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        pass
        # summarize_single_period(conn, 3600, int(time.time()))
        # summarize_single_period(conn, 43200, int(time.time()))
        # summarize_single_period(conn, 86400, int(time.time()))

if __name__ == '__main__':
    import argparse

    def valid_date(s):
        format = "%Y-%m-%d"
        try:
            return dt.datetime.strptime(s, format)
        except ValueError:
            msg = f'invalid date: {s}, expected in format {format}'
            raise argparse.ArgumentTypeError(msg)

    parser = argparse.ArgumentParser(prog=__file__)

    parser.add_argument('--debug', default=False, action='store_true')

    subparsers = parser.add_subparsers(help='sub-command help')
    parser_a = subparsers.add_parser('summarize-latest')
    parser_a.set_defaults(func=summarize_latest)
    parser_b = subparsers.add_parser('summarize-since')
    parser_b.add_argument('since', help='start date in YYYY-MM-DD format', type=valid_date)
    parser_b.set_defaults(func=summarize_since)

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    args.func(args)
