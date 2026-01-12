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
from pathlib import Path

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

# Historical data cache: {(timestamp, sensor, measurement_type): {'min': x, 'max': y, 'median': z}}
_historical_data = {}
_historical_sensors = set()


def load_historical_data(history_file):
    """Load historical daily summaries from TSV file."""
    global _historical_data, _historical_sensors

    history_path = Path(history_file)
    if not history_path.exists():
        print(f"Historical data file not found: {history_path}")
        return

    count = 0
    with open(history_path, 'r') as f:
        for line in f:
            if line.startswith('#') or line.startswith('timestamp\t'):
                continue
            parts = line.strip().split('\t')
            if len(parts) != 6:
                continue
            timestamp, sensor, measurement_type, min_val, max_val, median_val = parts
            key = (int(timestamp), sensor, measurement_type)
            _historical_data[key] = {
                'min': float(min_val),
                'max': float(max_val),
                'median': float(median_val),
            }
            _historical_sensors.add(sensor)
            count += 1

    print(f"Loaded {count:,} historical daily summaries for {len(_historical_sensors)} sensors")


def lookup_historical_daily_summaries(sensors, start, end, measurement_type):
    """Get daily summaries from historical data for the given range."""
    # Generate daily timestamps (start of each day) in the range
    DAY_SECS = 86400
    # Align to day boundaries
    start_day = (start // DAY_SECS) * DAY_SECS
    end_day = (end // DAY_SECS) * DAY_SECS

    timestamps = []
    sensor_values = {}

    day = start_day
    while day < end_day:
        has_data_for_day = False
        for sensor in sensors:
            key = (day, sensor, measurement_type)
            if key in _historical_data:
                data = _historical_data[key]
                sensor_values[f'{sensor}_min_{day}'] = data['min']
                sensor_values[f'{sensor}_max_{day}'] = data['max']
                sensor_values[f'{sensor}_median_{day}'] = data['median']
                has_data_for_day = True

        if has_data_for_day:
            timestamps.append(day)

        day += DAY_SECS

    return timestamps, sensor_values


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
        (start_dt.isoformat(), end_dt.isoformat())))])))

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
                                 ''', (sensor, start_dt.isoformat(), end_dt.isoformat())):
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
        for row in conn.execute(f'''SELECT period_start_at, minimum, maximum, median
                                    FROM hourly_{measurement_type}
                                    WHERE sensor = ? AND
                                          period_start_at >= ? AND
                                          period_start_at < ?
                                    ORDER BY period_start_at ASC
                                 ''', (sensor, start, end)):
            period_start_at, minimum, maximum, median = row
            sensor_values[f'{sensor}_min_{period_start_at}'] = minimum
            sensor_values[f'{sensor}_max_{period_start_at}'] = maximum
            sensor_values[f'{sensor}_median_{period_start_at}'] = median

    for sensor in sensors:
        min_row, max_row, median_row = [], [], []
        for ts in timestamps:
            min_row.append(sensor_values.get(f'{sensor}_min_{ts}', None))
            max_row.append(sensor_values.get(f'{sensor}_max_{ts}', None))
            median_row.append(sensor_values.get(f'{sensor}_median_{ts}', None))
        result.append(min_row)
        result.append(max_row)
        result.append(median_row)

    return result


def summary_json_query(parameters, file):
    pd = dict(parameters)
    start, end = int(pd['start']), int(pd['end'])
    measurement_type = measurement_type_matcher.match(pd['measurementType']).group(0)

    DAY_SECS = 86400

    with contextlib.closing(
            sqlite3.connect('measurement-summaries.db',
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)) as conn:

        # Get sensors from both DB and historical data
        db_sensors = set(r[0] for r in conn.execute('SELECT DISTINCT sensor FROM hourly_temperature'))
        all_sensors = sorted(db_sensors | _historical_sensors)

        # Get data from measurement-summaries.db
        matrix = result_matrix_from_hourly_summaries(conn, all_sensors, start, end, measurement_type)

        # Find which days are covered by DB data
        db_timestamps = set(matrix[0]) if matrix[0] else set()

        # Get historical data for days not in DB
        hist_timestamps, hist_values = lookup_historical_daily_summaries(all_sensors, start, end, measurement_type)

        # Filter to only timestamps not already in DB (align to day for comparison)
        db_days = set((ts // DAY_SECS) * DAY_SECS for ts in db_timestamps)
        missing_hist_timestamps = [ts for ts in hist_timestamps if ts not in db_days]

        if missing_hist_timestamps:
            # Merge historical data into the matrix
            all_timestamps = sorted(set(matrix[0]) | set(missing_hist_timestamps))
            new_matrix = [all_timestamps]

            for sensor in all_sensors:
                min_row, max_row, median_row = [], [], []
                for ts in all_timestamps:
                    if ts in db_timestamps:
                        # Get from existing matrix
                        old_idx = matrix[0].index(ts)
                        sensor_idx = all_sensors.index(sensor)
                        base_idx = 1 + sensor_idx * 3
                        min_row.append(matrix[base_idx][old_idx] if base_idx < len(matrix) else None)
                        max_row.append(matrix[base_idx + 1][old_idx] if base_idx + 1 < len(matrix) else None)
                        median_row.append(matrix[base_idx + 2][old_idx] if base_idx + 2 < len(matrix) else None)
                    else:
                        # Get from historical data
                        min_row.append(hist_values.get(f'{sensor}_min_{ts}', None))
                        max_row.append(hist_values.get(f'{sensor}_max_{ts}', None))
                        median_row.append(hist_values.get(f'{sensor}_median_{ts}', None))
                new_matrix.append(min_row)
                new_matrix.append(max_row)
                new_matrix.append(median_row)

            matrix = new_matrix

        file.write(json.dumps(
            {
                'data': matrix,
                'summaries': True,
                'sensors': all_sensors
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
    import argparse

    parser = argparse.ArgumentParser(
        description='HTTP server for measurement data visualization'
    )
    parser.add_argument(
        '--history-file',
        default='history-daily-summary.tsv',
        help='Path to historical daily summary TSV file (default: history-daily-summary.tsv)'
    )

    args = parser.parse_args()
    load_historical_data(args.history_file)
    run()
