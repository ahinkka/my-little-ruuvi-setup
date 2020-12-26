# My Little Ruuvi Setup

I.e. how I record and display the measurements collected from the excellent
Ruuvi sensors.

The main design driver for this project is that I want something *dirt simple*
and *easy to maintain*. Currently it requires one to copy four files to the Pi
and create an autostart script so that both the custom RuuviCollector and
Python script are started when the Pi boots up.

TBD and other musings:
 - Add autostart script to the repo.
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

*RuuviCollector* by is used for collecting measurements from the sensors.

See my [fork](https://github.com/ahinkka/RuuviCollector/) and the branch
[feature/sqlite-db-connection](
https://github.com/ahinkka/RuuviCollector/tree/feature/sqlite-db-connection)
for details.

With some packaging work I should be able to build a JAR that could use the
bog standard [RuuviCollector](https://github.com/Scrin/RuuviCollector), but I
haven't put the time into that yet as I'm kind of evaluating how it still
works and I'm not sure how stable of an interface is it that I'm using.


### Data management

The custom RuuviCollector stores the observations into an SQLite3
database. The create statements describing the database schema are in the
[collector
repository](https://github.com/ahinkka/RuuviCollector/blob/feature/sqlite-db-connection/src/main/resources/create-tables.sql).

SQLite was chosen as the storage backend as it's dead simple to operate, and
performant enough even on a Raspberry Pi.  I used to have a setup running on a
Pi based on InfluxDB, but at some point it just broke down due to the amount
of data, refused to start up due to running out of memory, and I ended up
losing the data. It might be possible to make InfluxDB run on a Raspberry Pi,
but I have no interest in learning how to do that as I think it's generally an
overkill for the use case. With SQLite I can keep it simple.


### Data visualization

Measurements are visualized using a single page application (SPA) served by
the Python script in this repo. The script contains both the HTTP server to
serve the SPA and the interface the SPA uses to request the actual measurement
data.

Measurement times are quantized to the minute (or when summaries are used, to
the summary's period) during query time to have matching timestamps between
different sensors for the visualization library.  Measurements have an
accurate (to the second) timestamp in the database.


# Licensing

The code directly connected to RuuviCollector is licensed under the same
license as the original RuuviCollector, MIT.  Other parts are under GPL3.
