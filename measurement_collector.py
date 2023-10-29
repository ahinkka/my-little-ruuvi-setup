#!/usr/bin/env python3
import asyncio
import binascii
import contextlib
import datetime as dt
import json
import logging
import statistics
import sqlite3
import traceback
from dataclasses import dataclass


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def table_name(measurement_type):
    return f'measurement_{measurement_type}'


def create_sql(measurement_type):
    return f'''CREATE TABLE IF NOT EXISTS {table_name(measurement_type)} (
  recorded_at INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  minimum REAL,
  maximum REAL,
  median REAL,
  mean REAL,
  CONSTRAINT recorded_at_sensor_pk PRIMARY KEY (recorded_at, sensor)
) WITHOUT ROWID
'''


def create_tables(conn):
    for quantity in ('temperature', 'pressure', 'humidity', 'voltage'):
        conn.execute(create_sql(quantity))
    conn.execute('''CREATE TABLE IF NOT EXISTS sensor (
                        sensor TEXT NOT NULL,
                        last_seen_at INTEGER NOT NULL,
                        CONSTRAINT sensor_pk PRIMARY KEY (sensor)
                    )''')
    conn.commit()


def extract_mac_address(obj):
    nums = obj['mac_address']
    return ''.join(["{0:0>2X}".format(n) for n in nums]).upper()


def extract_temperature(obj):
    value = obj.get('temperature_as_millikelvins', None)
    if value:
        # 0K − 273.15 = -273,1°C
        value = (value / 1000) - 273.15
    return value


def extract_pressure(obj):
    value = obj.get('pressure_as_pascals', None)
    if value:
        value = value / 100
    return value


def extract_humidity(obj):
    value = obj.get('humidity_as_ppm', None)
    if value:
        value = value / 10000.0
    return value


def extract_battery_voltage(obj):
    value = obj.get('battery_potential_as_millivolts', None)
    if value:
        value = value / 1000
    return value


@dataclass
class Measurement:
    recorded_at: dt.datetime
    value: float


async def handle(conn, obj, state):
    mac_address = extract_mac_address(obj)
    recorded_at = dt.datetime.now()

    conn.execute(f'''INSERT OR REPLACE INTO sensor (sensor, last_seen_at)
                     VALUES (?, ?)''',
                     (mac_address, recorded_at))

    temperature = extract_temperature(obj)
    pressure = extract_pressure(obj)
    humidity = extract_humidity(obj)
    voltage = extract_battery_voltage(obj)

    for quantity in ('temperature', 'pressure', 'humidity', 'voltage'):
        current = Measurement(
            recorded_at,
            value = locals()[quantity]
        )

        if mac_address not in state:
            state[mac_address] = {}
        if quantity not in state[mac_address]:
            state[mac_address][quantity] = []

        preceding_measurements = state[mac_address][quantity]
        previous = next(reversed(preceding_measurements), None)

        # logger.info('current', current)
        # logger.info('previous', previous)
        preceding_measurements.append(current)

        # if previous and previous.recorded_at.minute != current.recorded_at.minute:
        if previous and previous.recorded_at.hour != current.recorded_at.hour:
            # logger.info('hour changed')
            # logger.info(preceding_measurements)
            if len(preceding_measurements) > 0:
                values = [m.value for m in preceding_measurements]
                min_value = min(values)
                max_value = max(values)
                median_value = statistics.median(values)
                mean_value = statistics.mean(values)
                conn.execute(f'''
                    INSERT OR REPLACE INTO {table_name(quantity)}
                      (recorded_at, sensor, minimum, maximum, median, mean)
                    VALUES
                      (?, ?, ?, ?, ?, ?)
                ''', (
                    previous.recorded_at,
                    mac_address,
                    min_value,
                    max_value,
                    median_value,
                    mean_value
                ))
            state[mac_address][quantity] = []

    conn.commit()


async def main(host, port):
    state = {}

    while True: # maintain connection
        try:
            reader, writer = await asyncio.open_connection(host, port)

            with contextlib.closing(
                    sqlite3.connect('measurements.db',
                                    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
                create_tables(conn)

                while True: # receive lines
                    line = await asyncio.wait_for(reader.readline(), 120) # await for 120 seconds
                    logger.debug(f'Received: {line.decode()!r}')
                    obj = json.loads(line.decode())
                    await handle(conn, obj, state) # should there be a timeout here as well?

        except Exception as line_handling_error:
            traceback.print_exc()
            logger.info(
                'Encountered error in connecting or line reading loop, sleeping for 5 seconds before reconnecting. Error: %s',
                line_handling_error
            )

            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), 1)
            except Exception as e:
                logger.warn('Encountered error and ignored error while closing writer', e)

            await asyncio.sleep(5)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(prog=__file__)

    parser.add_argument('--hostname', default='localhost')
    parser.add_argument('--port', default=22222, type=int)
    parser.add_argument('--debug', default=False, action='store_true')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    asyncio.run(main(args.hostname, args.port))
