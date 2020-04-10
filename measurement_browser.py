#!/usr/bin/env python3
import contextlib
import json
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


def query(parameters):
    with contextlib.closing(
            sqlite3.connect('measurements.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        conn.row_factory = dict_factory
        return list(conn.execute('SELECT * FROM measurement'))


class MeasurementHandler(SimpleHTTPRequestHandler):
    def do_GET(self, *args, **kwargs):
        eff_path = self.path.replace('..', '')
        parsed = urlparse(eff_path)

        path_suffix = parsed.path.split('/')[-1]
        if path_suffix not in ALLOW_LIST:
            return self.send_error(403, message='Path not allowed', explain=None)

        if parsed.path.endswith('measurements'):
            self.send_header('Content-Type', 'application/json')
            self.wfile.write(
                json.dumps(
                    query(parse_qsl(parsed.query)),
                    ensure_ascii=False,
                    indent=4,
                    sort_keys=True
                ).encode('utf-8'))
            return

        return super().do_GET(*args, **kwargs)


def run(server_class=HTTPServer, handler_class=MeasurementHandler):
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == '__main__':
    run()
