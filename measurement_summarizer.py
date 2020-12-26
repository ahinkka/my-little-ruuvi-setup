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


def summarize_period_containing(conn, measurement_type, period_secs, containing_epoch_secs, overwrite=False):
    period_start = containing_epoch_secs - (containing_epoch_secs % period_secs)

    sensors = list(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM measurement'))

    for sensor in sensors:
        if len(conn.execute(f'SELECT 1 FROM {table_name(measurement_type, period_secs)} WHERE starts_at = ? AND sensor = ?', (period_start, sensor)).fetchall()) == 1:
            if overwrite is False:
                continue

        values = list(r[0] for r in conn.execute(f"SELECT {measurement_type} FROM measurement WHERE sensor = ? AND recorded_at >= ? AND recorded_at < ?", (sensor, period_start, period_start + period_secs)))

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


def summarize_single_period(conn, period_secs, epoch_secs_containing, overwrite=False):
        for measurement_type in [
                'temperature',
                'humidity',
                'pressure',
                # 'battery_voltage',
                # 'tx_power'
        ]:
            conn.execute(create_sql(measurement_type, period_secs))
            summarize_period_containing(conn, measurement_type, period_secs, epoch_secs_containing, overwrite=overwrite)


def summarize_latest(conn, args):
    summarize_single_period(conn, 3600, int(time.time()), overwrite=True)
    summarize_single_period(conn, 10800, int(time.time()), overwrite=True)
    summarize_single_period(conn, 86400, int(time.time()), overwrite=True)


def summarize_previous(conn, args):
    summarize_single_period(conn, 3600, int(time.time()) - 3600, overwrite=True)
    summarize_single_period(conn, 10800, int(time.time()) - 10800, overwrite=True)
    summarize_single_period(conn, 86400, int(time.time()) - 8600, overwrite=True)


def summarize_since(conn, args):
    arg_pairs = []
    for period_secs in [3600, 10800, 86400]:
        epochs = range(int(time.time()), int(args.since.timestamp()), -period_secs)
        for e in epochs:
            arg_pairs.append((period_secs, e))

    arg_pairs.sort(key=lambda x: x[1], reverse=True)

    started_at = dt.datetime.now()
    for index, pair in enumerate(arg_pairs):
        time_taken = (dt.datetime.now() - started_at).total_seconds()
        avg_time_per_item = time_taken / float(index + 1)
        time_to_go = (len(arg_pairs) - index) * avg_time_per_item

        period_secs, e = pair
        logger.info(f'Summarizing ({period_secs}, {e}), taken: {time_taken}s, to go: {time_to_go}s')
        summarize_single_period(conn, period_secs, e)


def clear_summaries(conn, args):
    tables = list(r[0] for r in conn.execute("select name from sqlite_master where type = 'table' and name like 'summary_%'"))

    for table in tables:
        conn.execute(f'drop table {table}')
        conn.commit()
        logger.info(f'Table {table} dropped')


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

    parser_a = subparsers.add_parser('summarize-previous')
    parser_a.set_defaults(func=summarize_previous)

    parser_b = subparsers.add_parser('summarize-since')
    parser_b.add_argument('since', help='start date in YYYY-MM-DD format', type=valid_date)
    parser_b.set_defaults(func=summarize_since)

    parser_c = subparsers.add_parser('clear-summaries')
    parser_c.set_defaults(func=clear_summaries)

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    with contextlib.closing(
            sqlite3.connect('measurements.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        args.func(conn, args)
