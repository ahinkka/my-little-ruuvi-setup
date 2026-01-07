#!/usr/bin/env python3
"""measurement_buffer_live_client.py - Live sensor statistics viewer"""

import argparse
import json
import sys
import time
import select
import termios
import tty
from statistics import median, mean
from urllib.request import urlopen
from urllib.error import URLError
from datetime import datetime

# ANSI color codes (colorblind-friendly palette)
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'
UNDERLINE = '\033[4m'
BLUE = '\033[34m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
CYAN = '\033[36m'
WHITE = '\033[37m'
MAGENTA = '\033[35m'

# Sortable columns: (key, header_text, width, is_right_aligned)
# Width must be >= len(header_text) to fit indicator
SORT_COLUMNS = [
    ('name', 'Sensor', 12, False),
    ('latest', 'Latest', 7, True),
    ('min', 'Min', 7, True),
    ('max', 'Max', 7, True),
    ('median', 'Median', 7, True),
    ('avg', 'Avg', 7, True),
    ('trend_1h', '1h', 7, True),
    ('trend_5m', '5m', 7, True),
    ('trend_1m', '1m', 7, True),
]


def parse_args():
    parser = argparse.ArgumentParser(
        description='Live viewer for measurement_buffer.py statistics'
    )
    parser.add_argument('--hostname', default='localhost',
                        help='Host where measurement_buffer.py is running (default: localhost)')
    parser.add_argument('--port', default=22223, type=int,
                        help='HTTP port of measurement_buffer.py (default: 22223)')
    parser.add_argument('--mode', default='temperature', choices=['temperature', 'humidity'],
                        help='Initial display mode (default: temperature)')
    parser.add_argument('--sensors-file', default='sensors.json',
                        help='Path to JSON file mapping sensor MACs to names (default: sensors.json)')
    return parser.parse_args()


def fetch_measurements(hostname, port):
    """Fetch measurements from the HTTP endpoint."""
    url = f'http://{hostname}:{port}/measurements.json'
    try:
        with urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        return None


def load_sensor_names(path):
    """Load sensor name mappings from a JSON file."""
    if not path:
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Extract name from each sensor entry
        return {mac: info.get('name', mac) for mac, info in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {}


def linear_regression_slope(times, values):
    """Calculate slope using least-squares linear regression."""
    n = len(times)
    if n < 2:
        return None

    sum_x = sum(times)
    sum_y = sum(values)
    sum_xy = sum(t * v for t, v in zip(times, values))
    sum_xx = sum(t * t for t in times)

    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope * 3600  # Convert to per-hour rate


def compute_statistics(data, mode):
    """Compute statistics for each sensor."""
    if not data or 'measurements' not in data or 'sensors' not in data:
        return {}

    measurements = data['measurements']
    sensors = data['sensors']
    now = time.time()

    # Group measurements by sensor
    by_sensor = {s: [] for s in sensors}
    for m in measurements:
        sensor = m['sensor']
        if sensor in by_sensor:
            value = m['temperature'] if mode == 'temperature' else m['humidity']
            by_sensor[sensor].append({
                'time': m['recorded_at'],
                'value': value
            })

    stats = {}
    for sensor in sensors:
        sensor_data = by_sensor[sensor]
        if not sensor_data:
            continue

        values = [d['value'] for d in sensor_data]
        times = [d['time'] for d in sensor_data]

        # Basic statistics
        latest = sensor_data[-1]['value'] if sensor_data else None
        min_val = min(values) if values else None
        max_val = max(values) if values else None
        median_val = median(values) if values else None
        avg_val = mean(values) if values else None

        # Trend calculations
        trend_1h = linear_regression_slope(times, values)

        # 5 minute trend
        cutoff_5m = now - 300
        data_5m = [(t, v) for t, v in zip(times, values) if t >= cutoff_5m]
        if len(data_5m) >= 2:
            times_5m, values_5m = zip(*data_5m)
            trend_5m = linear_regression_slope(list(times_5m), list(values_5m))
        else:
            trend_5m = None

        # 1 minute trend
        cutoff_1m = now - 60
        data_1m = [(t, v) for t, v in zip(times, values) if t >= cutoff_1m]
        if len(data_1m) >= 2:
            times_1m, values_1m = zip(*data_1m)
            trend_1m = linear_regression_slope(list(times_1m), list(values_1m))
        else:
            trend_1m = None

        stats[sensor] = {
            'latest': latest,
            'min': min_val,
            'max': max_val,
            'median': median_val,
            'avg': avg_val,
            'trend_1h': trend_1h,
            'trend_5m': trend_5m,
            'trend_1m': trend_1m,
        }

    return stats


def format_value(value, mode, width=9):
    """Format a measurement value with unit."""
    if value is None:
        text = '-'
    elif mode == 'temperature':
        text = f'{value:.1f}°'
    else:
        text = f'{value:.1f}%'
    return f'{text:>{width}}'


def format_trend(value, width=9):
    """Format a trend value with color."""
    if value is None:
        text = f'{"-":>{width}}'
        return f'{DIM}{text}{RESET}'

    if value > 0.05:
        color = GREEN
        sign = '+'
    elif value < -0.05:
        color = YELLOW
        sign = ''
    else:
        color = WHITE
        sign = '+' if value >= 0 else ''

    text = f'{sign}{value:.2f}'
    return f'{color}{text:>{width}}{RESET}'


def clear_screen():
    """Clear terminal screen."""
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


def render_display(stats, mode, hostname, port, sensor_names=None, sort_column=0, sort_reverse=False, error=None):
    """Render the statistics display."""
    clear_screen()

    if sensor_names is None:
        sensor_names = {}

    mode_display = 'Temperature' if mode == 'temperature' else 'Humidity'
    unit_hint = '°C/hour' if mode == 'temperature' else '%/hour'

    # Header
    print(f'{BOLD}{CYAN}measurement_buffer_live_client{RESET} - {BOLD}{mode_display}{RESET}')
    print(f'{DIM}Connected to {hostname}:{port}{RESET}')
    print(f'{DIM}Press {WHITE}t{DIM}/{WHITE}h{DIM} mode, {WHITE}<{DIM}/{WHITE}>{DIM} sort column, {WHITE}R{DIM} reverse, {WHITE}q{DIM} quit{RESET}')
    print(f'{DIM}Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{RESET}')
    print()

    if error:
        print(f'{YELLOW}Error: {error}{RESET}')
        print(f'{DIM}Retrying...{RESET}')
        return

    if not stats:
        print(f'{DIM}Waiting for data...{RESET}')
        return

    # Build table header with sort indicator
    # ▼ = descending (high to low), ▲ = ascending (low to high)
    sort_indicator = '▼' if sort_reverse else '▲'
    header_parts = []
    for i, (key, text, width, right_align) in enumerate(SORT_COLUMNS):
        indicator = sort_indicator if i == sort_column else ' '
        color = f'{BOLD}{CYAN}' if i == sort_column else BLUE
        col_width = width + 2
        # Left-aligned: indicator on right ("Sensor ▲")
        # Right-aligned: indicator on left ("▲ Latest")
        if right_align:
            text_with_ind = f'{indicator} {text}'
            col_text = f'{color}{text_with_ind:>{col_width}}{RESET}'
        else:
            text_with_ind = f'{text} {indicator}'
            col_text = f'{color}{text_with_ind:<{col_width}}{RESET}'
        header_parts.append(col_text)
    print(''.join(header_parts))
    print(f'{DIM}{"─" * 95}{RESET}')

    # Build sort key function
    sort_key_name = SORT_COLUMNS[sort_column][0]

    def get_sort_value(mac):
        if sort_key_name == 'name':
            return sensor_names.get(mac, mac).lower()
        else:
            val = stats[mac].get(sort_key_name)
            # Handle None values - put them at the end
            if val is None:
                return float('-inf') if sort_reverse else float('inf')
            return val

    sorted_sensors = sorted(stats.keys(), key=get_sort_value, reverse=sort_reverse)

    # Table rows - use width+2 to match header (accounts for indicator space)
    for sensor in sorted_sensors:
        s = stats[sensor]
        display_name = sensor_names.get(sensor, sensor)
        latest = format_value(s['latest'], mode)
        min_val = format_value(s['min'], mode)
        max_val = format_value(s['max'], mode)
        median_val = format_value(s['median'], mode)
        avg_val = format_value(s['avg'], mode)
        trend_1h = format_trend(s['trend_1h'])
        trend_5m = format_trend(s['trend_5m'])
        trend_1m = format_trend(s['trend_1m'])

        print(f'{WHITE}{display_name:<14}{RESET}{CYAN}{latest}{RESET}{min_val}{max_val}{median_val}{avg_val}{trend_1h}{trend_5m}{trend_1m}')

    print()
    print(f'{DIM}Trends are in {unit_hint}{RESET}')


class TerminalHandler:
    """Handle terminal raw mode for non-blocking keyboard input."""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = None

    def setup(self):
        """Enable raw mode."""
        try:
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        except termios.error:
            self.old_settings = None

    def restore(self):
        """Restore normal terminal mode."""
        if self.old_settings:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def get_key(self, timeout):
        """Get a keypress with timeout. Returns None if no key pressed."""
        try:
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                return sys.stdin.read(1)
        except (select.error, IOError):
            pass
        return None


def main():
    args = parse_args()
    mode = args.mode
    hostname = args.hostname
    port = args.port
    sensor_names = load_sensor_names(args.sensors_file)
    sort_column = 0
    sort_reverse = False

    terminal = TerminalHandler()
    terminal.setup()

    try:
        while True:
            # Fetch and display
            data = fetch_measurements(hostname, port)
            if data is None:
                render_display({}, mode, hostname, port, sensor_names, sort_column, sort_reverse, error='Failed to connect to server')
            else:
                stats = compute_statistics(data, mode)
                render_display(stats, mode, hostname, port, sensor_names, sort_column, sort_reverse)

            # Wait for keyboard input or timeout
            key = terminal.get_key(5.0)

            if key:
                if key.lower() == 'q':
                    break
                elif key.lower() == 't':
                    mode = 'temperature'
                elif key.lower() == 'h':
                    mode = 'humidity'
                elif key == '<' or key == ',':
                    sort_column = (sort_column - 1) % len(SORT_COLUMNS)
                elif key == '>' or key == '.':
                    sort_column = (sort_column + 1) % len(SORT_COLUMNS)
                elif key.upper() == 'R':
                    sort_reverse = not sort_reverse

    except KeyboardInterrupt:
        pass
    finally:
        terminal.restore()
        clear_screen()
        print('Goodbye!')


if __name__ == '__main__':
    main()
