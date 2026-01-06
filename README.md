# My Little Ruuvi Setup

I.e. how I record and display the measurements collected from the excellent
Ruuvi sensors.

The main design driver for this project is that I want something *dirt simple*
and *easy to maintain*. Currently it requires one to just copy a bunch of
files and create an autostart script so that both everything works on a
Raspberry Pi.

TBD and other musings:
 - Currently everything runs on a Raspberry Pi 3B rev 1.3, but the plan is to
   set up an SCP to copy over the files to a proper server so I could access
   the data outside my home network.
 - In addition to that, there needs to be some kind of day or week or month
   based versioning of the data at that point so that the SCP job stays fast.
 - There's currently no old data cleanup. While there's plenty of space on the
   SD the Pi runs from, it's not exactly a safe place to store data in the
   long term.


## Components

### Measurement collection

[*ruuvitag-jsonl-socket-bridge*](https://github.com/ahinkka/ruuvitag-jsonl-socket-bridge)
is used for collecting measurements from the sensors.


### Data management

*measurement_collector.py* stores the observations into an SQLite3

SQLite was chosen as the storage backend as it's dead simple to operate, and
performant enough even on a Raspberry Pi.  I used to have a setup running on a
Pi based on InfluxDB, but at some point it just broke down due to the amount
of data, refused to start up due to running out of memory, and I ended up
losing the data. It might be possible to make InfluxDB run on a Raspberry Pi,
but I have no interest in learning how to do that as I think it's generally an
overkill for the use case. With SQLite I can keep it simple.


### Recent data buffering and access

*measurement_buffer.py* maintains an in-memory buffer of recent temperature and
humidity measurements for the past hour, accessible via HTTP on port 22223.


### Data visualization

Measurements are visualized using a single page application (SPA) served by
*measurement_browser.py*. The script contains both the HTTP server to serve
the SPA and the interface the SPA uses to request the actual measurement data.

Measurement times are quantized to the minute (or when summaries are used, to
the summary's period) during query time to have matching timestamps between
different sensors for the visualization library.  Measurements have an
accurate timestamp in the database.


## Installation incantations

```
loginctl enable-linger
mkdir -p ~/.config/systemd/user/
# scp .service files into that dir
systemctl --user enable measurement_collector.service
systemctl --user enable measurement_browser.service
systemctl --user enable measurement_buffer.service
systemctl --user start measurement_collector
systemctl --user start measurement_browser
systemctl --user start measurement_buffer
systemctl --user status

# If you make changes to service files to e.g. enable debug logging, the
# following will take care of that:
systemctl --user daemon-reload
systemctl --user restart measurement_collector
systemctl --user restart measurement_browser
systemctl --user restart measurement_buffer

# To access the logs of the services:
journalctl --user -u measurement_collector
journalctl --user -u measurement_browser
journalctl --user -u measurement_buffer
```


## Licensing

This piece of software is licensed under GPLv3.
