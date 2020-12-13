#!/usr/bin/env python3
import contextlib
import json
import re
import sqlite3

from http.server import *
from urllib.parse import urlparse, parse_qsl

ALLOW_LIST = [
    'index.html',
    'style.css',
    'spa.js',
    'uPlot.min.css',
    'uPlot.iife.min.js',
    'measurements.json'
]


# https://stackoverflow.com/a/3300514
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def stringify(v):
    if v is None:
        return 'NaN'
    else:
        return str(v)


join_template = '''
LEFT JOIN quantified_values AS {sensor_alias} ON
    {sensor_alias}.sensor = '{sensor_id}'
  AND
    {sensor_alias}.recorded_at = quantified_values.recorded_at
'''

query_template = '''
WITH
  quantified_values AS (
    SELECT CAST((recorded_at / 60) AS INTEGER) * 60 AS recorded_at, sensor, {measurement_type}
    FROM measurement
    WHERE recorded_at >= ? AND recorded_at < ?
    GROUP BY CAST((recorded_at / 60) AS INTEGER) * 60, sensor
  )

SELECT DISTINCT
  quantified_values.recorded_at,
  {cols}

FROM quantified_values

{joins}
'''


def create_sql(measurement_type, sensors):
    col_template = '{sensor_alias}.{measurement_type}'

    return query_template.format(
        measurement_type=measurement_type,
        cols=',\n  '.join(
            col_template.format(
                sensor_alias='s' + str(idx),
                measurement_type=measurement_type,
            )
            for idx, sensor in enumerate(sensors)
        ),
        joins=''.join(
            join_template.format(
                sensor_alias='s' + str(idx),
                sensor_id=sensor
            )
            for idx, sensor in enumerate(sensors)
        )
    )


def result_matrix_from_measurements(conn, sensors, start, end, measurement_type):
    result = [[]]
    for sensor in sensors:
        result.append([])

    for row in conn.execute(create_sql(measurement_type, sensors), (start, end)):
        result[0].append(row[0])
        for idx, value in enumerate(row[1:]):
            result[idx + 1].append(value)

    return result


def summary_table_name(measurement_type, period_secs):
    return f"summary_{measurement_type}_{period_secs}"


summary_join_template = '''
LEFT JOIN {table_name} AS {sensor_alias} ON
    {sensor_alias}.sensor = '{sensor_id}'
  AND
    s.starts_at == {sensor_alias}.starts_at
'''

summary_query_template = '''
SELECT
  s.starts_at,
  {cols}

FROM {table_name} AS s
{joins}
WHERE
  s.starts_at >= ? AND s.starts_at < ?
'''

def create_summary_sql(measurement_type, sensors, window_secs):
    col_template = '{sensor_alias}.min_value, {sensor_alias}.max_value, {sensor_alias}.mean_value'
    table_name = summary_table_name(measurement_type, window_secs)
    return summary_query_template.format(
        table_name=table_name,
        cols=',\n  '.join(
            col_template.format(
                sensor_alias='s' + str(idx),
                measurement_type=measurement_type,
            )
            for idx, sensor in enumerate(sensors)
        ),
        joins=''.join(
            summary_join_template.format(
                table_name=table_name,
                sensor_alias='s' + str(idx),
                sensor_id=sensor
            )
            for idx, sensor in enumerate(sensors)
        )
    )


def result_matrix_from_summaries(conn, sensors, start, end, measurement_type, window):
    result = [[]]

    for sensor in sensors:
        result.append([])
        result.append([])
        result.append([])

    for row in conn.execute(create_summary_sql(measurement_type, sensors, window), (start, end)):
        result[0].append(row[0])
        for idx, value in enumerate(row[1:]):
            result[idx + 1].append(value)

    return result


def resolve_window(start, end):
    period_secs = end - start
    if period_secs < 86400:
        return 60
    elif period_secs < 7 * 86400:
        return 3600
    elif period_secs < 32 * 86400:
        return 10800
    else:
        return 86400


measurement_type_matcher = re.compile(r'[a-z_]{1,20}')
def json_query(parameters, file):
    pd =  dict(parameters)
    start, end = int(pd['start']), int(pd['end'])
    measurement_type = measurement_type_matcher.match(pd['measurementType']).group(0)

    with contextlib.closing(
            sqlite3.connect('measurements.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:

        sensors = sorted(list(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM measurement')))

        window = resolve_window(start, end)
        summaries = False
        if window == 60:
            matrix = result_matrix_from_measurements(conn, sensors, start, end, measurement_type)
        else:
            matrix = result_matrix_from_summaries(conn, sensors, start, end, measurement_type, window)
            summaries = True

        file.write(json.dumps(
            {
                'data': matrix,
                'summaries': summaries,
                'sensors': sensors
            }
        ).encode('utf-8'))


class MeasurementHandler(SimpleHTTPRequestHandler):
    def do_GET(self, *args, **kwargs):
        self.close_connection = True

        eff_path = self.path.replace('..', '')
        parsed = urlparse(eff_path)

        path_suffix = parsed.path.split('/')[-1]
        if path_suffix not in ALLOW_LIST:
            return self.send_error(403, message='Path not allowed', explain=None)

        if parsed.path.endswith('measurements.json'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            json_query(parse_qsl(parsed.query), self.wfile)
            return

        return super().do_GET(*args, **kwargs)


def run(server_class=HTTPServer, handler_class=MeasurementHandler):
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == '__main__':
    run()
