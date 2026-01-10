#!/usr/bin/env python3
import contextlib
import json
import math
import re
import sqlite3
import time
import datetime as dt

from http.server import *
from urllib.parse import urlparse, parse_qsl

ALLOW_LIST = [
    'index.html',
    'style.css',
    'spa.js',
    'uPlot.min.css',
    'uPlot.iife.min.js',
    'measurements.json',
    'summaries.json',
    'sensors.json'
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


def round_to_minute(dt_):
    return dt_.replace(second=0, microsecond=0, minute=dt_.minute, hour=dt_.hour)


def result_matrix_from_measurements(conn, sensors, start, end, measurement_type):
    start_dt = dt.datetime.fromtimestamp(start)
    end_dt = dt.datetime.fromtimestamp(end)

    dts = sorted(list(set([round_to_minute(dt.datetime.fromisoformat(dt_[0]))
           for dt_ in list(conn.execute(
        f'''SELECT recorded_at
            FROM measurement_{measurement_type}
            WHERE recorded_at >= ? AND
            recorded_at < ?''',
        (start_dt, end_dt)))])))

    # int(_dt.timestamp())
    result = [[int(_dt.timestamp()) for _dt in dts]]

    sensor_values = {}
    for sensor in sensors:
        for row in conn.execute(f'''SELECT recorded_at, median AS value
                                    FROM measurement_{measurement_type}
                                    WHERE sensor = ? AND
                                          recorded_at >= ? AND
                                          recorded_at < ?
                                    ORDER BY recorded_at ASC
                                 ''', (sensor, start_dt, end_dt)):
            recorded_at, value = row
            recorded_at_dt = round_to_minute(dt.datetime.fromisoformat(recorded_at))
            sensor_values[f'{sensor}, {recorded_at_dt.timestamp()}'] = value

    for sensor in sensors:
        sensor_row = []
        for dt_ in dts:
            sensor_row.append(
                sensor_values.get(f'{sensor}, {dt_.timestamp()}', None)
            )
        result.append(sensor_row)

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

    now_epoch_secs = math.floor(time.time())
    for row in conn.execute(create_summary_sql(measurement_type, sensors, window), (start, end)):
        # Generally we want to show the summary as the end of the summary as
        # it's basically looking back and summarizing that time. For the last
        # summary, though, as it's basically to this current time, it makes
        # more sense to limit it to current time.
        summary_starts_at = row[0]
        eff_summary_end = summary_starts_at + window
        if now_epoch_secs < eff_summary_end:
            eff_summary_end = now_epoch_secs

        result[0].append(eff_summary_end)
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

        sensors = sorted(list(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM sensor')))

        window = resolve_window(start, end)
        summaries = False
        # if window < 86400:
        matrix = result_matrix_from_measurements(conn, sensors, start, end, measurement_type)
        # else:
        #     matrix = result_matrix_from_summaries(conn, sensors, start, end, measurement_type, window)
        #     summaries = True

        file.write(json.dumps(
            {
                'data': matrix,
                'summaries': summaries,
                'sensors': sensors
            }
        ).encode('utf-8'))


def result_matrix_from_hourly_summaries(conn, sensors, start, end, measurement_type):
    timestamps = sorted(list(set([row[0]
           for row in conn.execute(
        f'''SELECT period_start_at
            FROM hourly_{measurement_type}
            WHERE period_start_at >= ? AND
            period_start_at < ?''',
        (start, end))])))

    result = [timestamps]

    sensor_values = {}
    for sensor in sensors:
        for row in conn.execute(f'''SELECT period_start_at, median AS value
                                    FROM hourly_{measurement_type}
                                    WHERE sensor = ? AND
                                          period_start_at >= ? AND
                                          period_start_at < ?
                                    ORDER BY period_start_at ASC
                                 ''', (sensor, start, end)):
            period_start_at, value = row
            sensor_values[f'{sensor}, {period_start_at}'] = value

    for sensor in sensors:
        sensor_row = []
        for ts in timestamps:
            sensor_row.append(
                sensor_values.get(f'{sensor}, {ts}', None)
            )
        result.append(sensor_row)

    return result


def summary_json_query(parameters, file):
    pd = dict(parameters)
    start, end = int(pd['start']), int(pd['end'])
    measurement_type = measurement_type_matcher.match(pd['measurementType']).group(0)

    with contextlib.closing(
            sqlite3.connect('measurement-summaries.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:

        sensors = sorted(list(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM hourly_temperature')))

        matrix = result_matrix_from_hourly_summaries(conn, sensors, start, end, measurement_type)

        file.write(json.dumps(
            {
                'data': matrix,
                'summaries': True,
                'sensors': sensors
            }
        ).encode('utf-8'))


class MeasurementHandler(SimpleHTTPRequestHandler):
    def do_GET(self, *args, **kwargs):
        self.close_connection = True

        eff_path = self.path.replace('..', '')
        parsed = urlparse(eff_path)

        if parsed.path == '/' or parsed.path == '':
            self.path = '/index.html'
            return super().do_GET(*args, **kwargs)

        path_suffix = parsed.path.split('/')[-1]
        if path_suffix not in ALLOW_LIST:
            return self.send_error(403, message='Path not allowed', explain=None)

        if parsed.path.endswith('measurements.json'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            json_query(parse_qsl(parsed.query), self.wfile)
            return

        if parsed.path.endswith('summaries.json'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            summary_json_query(parse_qsl(parsed.query), self.wfile)
            return

        return super().do_GET(*args, **kwargs)


def run(server_class=HTTPServer, handler_class=MeasurementHandler):
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()


if __name__ == '__main__':
    run()
