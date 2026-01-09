#!/usr/bin/env python3
import asyncio
import datetime as dt
import json
import logging
import sqlite3
import threading
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_tables(conn):
    conn.execute('''CREATE TABLE measurement (
        recorded_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
        sensor TEXT NOT NULL,
        temperature REAL NOT NULL,
        humidity REAL NOT NULL,
        CONSTRAINT recorded_at_sensor_pk PRIMARY KEY (recorded_at, sensor)
    ) WITHOUT ROWID''')
    conn.execute('CREATE INDEX idx_recorded_at ON measurement(recorded_at)')


def cleanup_old_entries(conn):
    max_age = dt.timedelta(hours=24, minutes=15)
    cutoff = int(time.time()) - int(max_age.total_seconds())
    conn.execute('DELETE FROM measurement WHERE recorded_at < ?', (cutoff,))


def extract_mac_address(obj):
    nums = obj['mac_address']
    return ''.join(["{0:0>2X}".format(n) for n in nums]).upper()


def extract_temperature(obj):
    value = obj.get('temperature_as_millikelvins', None)
    if value:
        value = (value / 1000) - 273.15
    return value


def extract_humidity(obj):
    value = obj.get('humidity_as_ppm', None)
    if value:
        value = value / 10000.0
    return value


async def handle(conn, lock, obj):
    mac_address = extract_mac_address(obj)

    temperature = extract_temperature(obj)
    humidity = extract_humidity(obj)

    if temperature is None or humidity is None:
        logger.debug(f'Skipping measurement from {mac_address}: temperature={temperature}, humidity={humidity}')
        return

    with lock:
        conn.execute('''INSERT INTO measurement (sensor, temperature, humidity)
                        VALUES (?, ?, ?)''',
                     (mac_address, temperature, humidity))
        cleanup_old_entries(conn)
        conn.commit()


def get_measurements_json(conn, lock):
    max_age = dt.timedelta(hours=1)
    cutoff = int(time.time()) - int(max_age.total_seconds())
    with lock:
        rows = conn.execute('''SELECT recorded_at, sensor, temperature, humidity
                               FROM measurement
                               WHERE recorded_at >= ?
                               ORDER BY recorded_at ASC''', (cutoff,)).fetchall()

    measurements = {}
    for r in rows:
        sensor = r[1]
        if sensor not in measurements:
            measurements[sensor] = []
        measurements[sensor].append({
            'recorded_at': r[0],
            'temperature': r[2],
            'humidity': r[3]
        })

    return json.dumps(measurements)


class BufferHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/measurements.json' or self.path.startswith('/measurements.json?'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = get_measurements_json(self.server.conn, self.server.lock)
            self.wfile.write(response.encode('utf-8'))
        else:
            self.send_error(404, 'Not Found')

    def log_message(self, format, *args):
        logger.debug(f'HTTP: {format % args}')


def run_http_server(conn, lock, port):
    server_address = ('', port)
    httpd = HTTPServer(server_address, BufferHandler)
    httpd.conn = conn
    httpd.lock = lock
    logger.info(f'HTTP server listening on port {port}')
    httpd.serve_forever()


async def main(host, port, http_port):
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    lock = threading.Lock()
    create_tables(conn)
    conn.commit()

    http_thread = threading.Thread(target=run_http_server, args=(conn, lock, http_port), daemon=True)
    http_thread.start()

    while True:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            logger.info(f'Connected to {host}:{port}')

            while True:
                line = await asyncio.wait_for(reader.readline(), 120)
                if not line:
                    logger.info('Connection closed by server')
                    break
                logger.debug(f'Received: {line.decode()!r}')
                obj = json.loads(line.decode())
                await handle(conn, lock, obj)

        except Exception as e:
            traceback.print_exc()
            logger.info(
                'Encountered error in connecting or line reading loop, sleeping for 5 seconds before reconnecting. Error: %s',
                e
            )

            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), 1)
            except Exception:
                pass

            await asyncio.sleep(5)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(prog=__file__)
    parser.add_argument('--hostname', default='localhost')
    parser.add_argument('--port', default=22222, type=int)
    parser.add_argument('--http-port', default=22223, type=int)
    parser.add_argument('--debug', default=False, action='store_true')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    asyncio.run(main(args.hostname, args.port, args.http_port))
