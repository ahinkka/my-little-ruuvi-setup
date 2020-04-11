#!/usr/bin/env python3
import contextlib
import json
import re
import sqlite3

from http.server import *
from urllib.parse import urlparse, parse_qsl

ALLOW_LIST = [
    'index.html',
    'spa.js',
    'measurements'
]


# https://stackoverflow.com/a/3300514
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


measurement_type_matcher = re.compile(r'[a-z_]{1,20}')
# https://www.sqlite.org/windowfunctions.html
def query(parameters):
    pd =  dict(parameters)

    measurement_type = measurement_type_matcher.match(pd['measurementType']).group(0)
    with contextlib.closing(
            sqlite3.connect('measurements.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        conn.row_factory = dict_factory
        return list(conn.execute(
            'SELECT recorded_at, sensor, ' +
            measurement_type +
            ' FROM measurement WHERE recorded_at >= ? AND recorded_at < ?',
            (int(pd['start']), int(pd['end']))
        ))


class MeasurementHandler(SimpleHTTPRequestHandler):
    def do_GET(self, *args, **kwargs):
        self.close_connection = True

        eff_path = self.path.replace('..', '')
        parsed = urlparse(eff_path)

        path_suffix = parsed.path.split('/')[-1]
        if path_suffix not in ALLOW_LIST:
            return self.send_error(403, message='Path not allowed', explain=None)

        if parsed.path.endswith('measurements'):
            output = json.dumps(query(parse_qsl(parsed.query)), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(output))
            self.end_headers()
            self.wfile.write(output)
            return

        return super().do_GET(*args, **kwargs)


def run(server_class=HTTPServer, handler_class=MeasurementHandler):
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == '__main__':
    run()
