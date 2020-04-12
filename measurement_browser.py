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


query_template = '''
WITH
  rounded_with_duplicates AS (
    SELECT
      CAST((recorded_at / {selection_coef}) AS INTEGER) * {selection_coef} AS rounded_recorded_at,
      sensor,
      rowid
    FROM measurement
    WHERE
      recorded_at >= ?
    AND
      recorded_at < ?
  ),
  unique_rowids AS (SELECT DISTINCT rowid FROM rounded_with_duplicates GROUP BY rounded_recorded_at, sensor)

SELECT
  recorded_at,
  CAST((recorded_at / {rounding_coef}) AS INTEGER) * {rounding_coef} AS recorded_at,
  sensor,
  {measurement_type}
FROM measurement
WHERE
  rowid IN (SELECT * FROM unique_rowids)
'''


measurement_type_matcher = re.compile(r'[a-z_]{1,20}')
# https://www.sqlite.org/windowfunctions.html
def query(parameters):
    pd =  dict(parameters)

    start, end = int(pd['start']), int(pd['end'])
    coef = 1
    if end - start > 50 * 60:
        coef = 10
    elif end - start > 11 * 60 * 60:
        coef = 100
    elif end - start > 23 * 60 * 60:
        coef = 1000
    elif end - start > 47 * 60 * 60:
        coef = 10000

    measurement_type = measurement_type_matcher.match(pd['measurementType']).group(0)
    with contextlib.closing(
            sqlite3.connect('measurements.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:
        conn.row_factory = dict_factory
        return list(conn.execute(
            query_template.format(rounding_coef=coef, selection_coef=coef, measurement_type=measurement_type),
            (start, end)
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
