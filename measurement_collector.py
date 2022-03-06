#!/usr/bin/env python3
import asyncio
import binascii
import contextlib
import datetime as dt
import json
import math
import sqlite3
import time
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


async def persist(conn, obj):
    mac_address = extract_mac_address(obj)
    recorded_at = dt.datetime.now()

    temperature = extract_temperature(obj)
    pressure = extract_pressure(obj)
    humidity = extract_humidity(obj)
    voltage = extract_battery_voltage(obj)

    logger.info((mac_address, recorded_at, temperature, pressure, humidity, voltage))


async def main(host, port):
    while True: # maintain connection
        try:
            reader, writer = await asyncio.open_connection(host, port)

            with contextlib.closing(
                    sqlite3.connect('measurements.db',
                                    detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:

                while True: # receive lines
                    line = await asyncio.wait_for(reader.readline(), 120) # await for 120 seconds
                    logger.debug(f'Received: {line.decode()!r}')
                    obj = json.loads(line.decode())
                    await persist(conn, obj) # should there be a timeout here as well?

        except Exception as line_handling_error:
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
