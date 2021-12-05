#!/usr/bin/env python3
import contextlib
import sqlite3
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MEASUREMENT_TYPES = ('temperature', 'pressure', 'humidity', 'battery_voltage')


def create_sql(measurement_type):
    return f"""CREATE TABLE IF NOT EXISTS {measurement_type} (
  recorded_at INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  value REAL,
  CONSTRAINT recorded_at_sensor_pk PRIMARY KEY (recorded_at, sensor)
) WITHOUT ROWID
"""


def star_schemify(src, dest):
    sensors = list(r[0] for r in src.execute('SELECT DISTINCT sensor FROM measurement'))
    for measurement_type in MEASUREMENT_TYPES:
        dest.execute(create_sql(measurement_type))
        dest.commit()
        logger.info(f'Created table for {measurement_type=}')

        for idx, row in enumerate(src.execute(
                f"SELECT recorded_at, sensor, {measurement_type} AS value FROM measurement",)):
            recorded_at, sensor, value = row

            insert_sql = f"""INSERT INTO {measurement_type} (recorded_at, sensor, value)
                             VALUES (?, ?, ?)
                             ON CONFLICT DO NOTHING"""
            dest.execute(
                insert_sql,
                (recorded_at, sensor, value)
            )

            if idx % 100000 == 0:
                dest.commit()
                logger.info(f'Processed {idx} items for measurement type')

        dest.commit()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(prog=__file__)
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--debug', default=False, action='store_true')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    with contextlib.closing(
            sqlite3.connect(args.source,
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as src:
        with contextlib.closing(
                sqlite3.connect(args.destination,
                                detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as dest:
            star_schemify(src, dest)
