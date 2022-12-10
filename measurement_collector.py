#!/usr/bin/env python3
import asyncio
import binascii
import contextlib
import datetime as dt
import json
import logging
import math
import sqlite3
import time
import traceback


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def table_name(measurement_type):
    return f'measurement_{measurement_type}'


def create_sql(measurement_type):
    return f'''CREATE TABLE IF NOT EXISTS {table_name(measurement_type)} (
  recorded_at INTEGER NOT NULL,
  sensor TEXT NOT NULL,
  value REAL,
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


QUANTITY_CHANGE_THRESHOLD = {
    'temperature': 0.02,
    'pressure': 0.03,
    'humidity': 0.1,
    'voltage': 0.05
}


async def persist(conn, obj):
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
        value = locals()[quantity]
        cur = conn.cursor()
        rows = list(cur.execute(f'''SELECT recorded_at, value FROM {table_name(quantity)}
                                    WHERE sensor = ?
                                    ORDER BY recorded_at DESC LIMIT 2''',
                                (mac_address,)))
        if len(rows) == 2:
            last_recorded_at, last_value = list(rows)[0]
            last_recorded_at_dt = dt.datetime.fromisoformat(last_recorded_at)
            second_to_last_recorded_at, second_to_last_value = list(rows)[1]
            second_to_last_recorded_at_dt = dt.datetime.fromisoformat(second_to_last_recorded_at)

            time_between = last_recorded_at_dt - second_to_last_recorded_at_dt
            time_since_last = recorded_at - last_recorded_at_dt

            if (time_between < dt.timedelta(hours=1) and
                time_since_last < dt.timedelta(hours=1) and
                math.isclose(last_value, value,
                             rel_tol=QUANTITY_CHANGE_THRESHOLD[quantity])):
                logger.debug(f'Delete previous {quantity} for sensor {mac_address}')
                conn.execute(f'''DELETE FROM {table_name(quantity)}
                                 WHERE recorded_at = ? AND sensor = ?''',
                             (last_recorded_at_dt, mac_address))

        conn.execute(f'''INSERT OR REPLACE INTO {table_name(quantity)}
                                (recorded_at, sensor, value)
                         VALUES
                                (?, ?, ?)''',
                     (recorded_at, mac_address, value))
    conn.commit()


async def main(host, port):
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
                    await persist(conn, obj) # should there be a timeout here as well?

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
