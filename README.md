# wxvx

A workflow tool for weather-model verification, leveraging [`uwtools`](https://github.com/ufs-community/uwtools) to drive [MET](https://github.com/dtcenter/MET) and [METplus](https://github.com/dtcenter/METplus).

## Installation

1. Download, install, and activate [Miniforge](https://github.com/conda-forge/miniforge), the [conda-forge](https://conda-forge.org/) project's implementation of [Miniconda](https://docs.anaconda.com/miniconda/). This step can be skipped if you already have a conda installation you want to use. Linux `aarch64` and `x86_64` systems are currently supported. The example shown below is for a Linux `aarch64` system, so if your system is Intel/AMD, download the `x86_64` installer.

``` bash
wget https://github.com/conda-forge/miniforge/releases/download/25.3.0-3/Miniforge3-Linux-aarch64.sh
bash Miniforge3-Linux-aarch64.sh -bfp conda
rm Miniforge3-Linux-aarch64.sh
. conda/etc/profile.d/conda.sh
conda activate
```

**NOTE:** If you need a development environment in which to develop and test `wxvx` code, skip the following step and refer to the [Development](#development) section.

2. Create and activate a conda virtual environment providing the latest `wxvx`. (Add the flags `-c conda-forge --override-channels` to the `conda create` command if you are using a non-conda-forge conda installation.)

``` bash
conda create -y -n wxvx -c ufs-community -c paul.madden wxvx
conda activate wxvx
wxvx --version
```

The activated virtual environment includes the [`met2go`](https://github.com/maddenp-cu/met2go) package, which provides [MET](https://github.com/dtcenter/MET) and select [METplus](https://github.com/dtcenter/METplus) executables and data files. See the `met2go` [docs](https://github.com/maddenp-cu/met2go/blob/main/README.md) for more information.

## Configuration

An overview of the content of the YAML configuration file specified via `-c` / `--config` is described in the table below. See the subsections below for more detailed information. Use the `-s` / `--show` CLI switch to show a pro-forma config with sample values for reference.

```
┌────────────────────┬───────────────────────────────────────────┐
│ Key                │ Description                               │
├────────────────────┼───────────────────────────────────────────┤
│ baseline:          │ Description of the baseline dataset       │
│   compare:         │   Verify and/or plot forecast?            │
│   name:            │   Dataset descriptive name                │
│   url:             │   Template for baseline GRIB location     │
│ cycles:            │ Cycles to verify                          │
│   start:           │   First cycle                             │
│   step:            │   Interval between cycles                 │
│   stop:            │   Last cycle                              │
│ forecast:          │ Description of the forecast dataset       │
│   coords:          │   Names of coordinate variables           │
│     latitude:      │     Latitude variable                     │
│     level:         │     Level variable                        │
│     longitude:     │     Longitude variable                    │
│     time:          │     Names of time variables               │
│       inittime:    │       Forecast initialization time        │
│       leadtime:    │       Forecast leadtime                   │
│       validtime:   │       Forecast validtime                  │
│   mask:            │   Sequence of [lat, lon] pairs (optional) │
│   name:            │   Dataset descriptive name                │
│   path:            │   Filesystem path to Zarr/netCDF dataset  │
│   projection:      │   Projection information                  │
│ leadtimes:         │ Leadtimes to verify                       │
│   start:           │   First leadtime                          │
│   step:            │   Interval between leadtimes              │
│   stop:            │   Last leadtime                           │
│ meta:              │ Optional free-form data section           │
│ paths:             │ Paths                                     │
│   grids:           │   Where to store grids                    │
│     baseline:      │     Baseline grids                        │
│     forecast:      │     Forecast grids                        │
│   run:             │   Where to store run data                 │
│ regrid:            │ MET regrid options                        │
│   method:          │   Regridding method                       │
│   to:              │   Destination grid                        │
│ variables:         │ Mapping describing variables to verify    │
│   VAR:             │   Forecast-dataset variable name          │
│     level_type:    │     Generic level type                    │
│     levels:        │     Sequence of level values              │
│     name:          │     Canonical variable name               │
└────────────────────┴───────────────────────────────────────────┘
```

### baseline.url

The `baseline.url` value may include Jinja2 expressions, processed at run-time with [`jinja2.Tremplate.render()`](https://jinja.palletsprojects.com/en/stable/api/#jinja2.Template.render). Variables `yyyymmdd` (cycle date, a `str`), `hh` (cycle time, a `str`), and `fh` (forecast hour, aka leadtime, an `int`) will be supplied by `wxvx`.

### cycles

The `start` and `stop` values should be in optionally quoted [ISO8601](https://en.wikipedia.org/wiki/ISO_8601) year/month/date/hour/minute/second form, e.g. `2025-06-03T12:00:00`. The `step` value should be either an `int` specifying the number of hours, or a quoted string of the form `hours[:minutes[:seconds]]` specifying hours and, optionally, minutes and seconds.

When using `start` / `step` / `stop` syntax, the final cycle is included in verification. That is, the range is inclusive of its upper bound.

Alternatively, the cycles to verify may be specified as an arbitrary list of ISO8601-formatted values, e.g.

``` yaml
cycles:
  - 2025-06-01T06:00:00
  - 2025-06-02T12:00:00
  - 2025-06-03T18:00:00
```

or

``` yaml
cycles: [2025-06-01T06:00:00, 2025-06-02T12:00:00, 2025-06-03T18:00:00]
```

### forecast.coords.time

Specify values under `forecast.coords.time` as follows:

  - `inittime`: The name of the variable or attribute providing the forecast initialization time, aka cycle or, per CF Conventions, forecast reference time. Required.
  - `leadtime`: The name of the variable or attribute providing the forecast leadtime. Exactly one of `leadtime` and `validtime` must be specified.
  - `validtime`: The name of the variable or attribute providing the forecast validtime. Exactly one of `validtime` and `leadtime` must be specified.

If a variable specified under `forecast.coords.time` names a coordinate dimension variable, that variable will be used. If no such variable exists, `wxvx` will look for a dataset attribute with the given name and try to use it, coercing it to the expected type (e.g. `datetime` or `timedelta`) as needed. For example, it will parse an ISO8601-formatted string to a Python `datetime` object.

### forecast.mask

The `forecast.mask` value may be omitted, or set to the YAML value `null`, in which case no masking will be applied.

### forecast.path

The `forecast.path` value may include Python string-template expressions, processed at run-time with [`str.format()`](https://docs.python.org/3/library/stdtypes.html#str.format). Variables `yyyymmdd` (cycle date, a `str`), `hh` (cycle time, a `str`), and `fh` (forecast hour, aka leadtime, an `int`) will be supplied by `wxvx`.

### leadtimes

Each value should be either an `int` specifying the number of hours, or a **quoted string** of the form `hours[:minutes[:seconds]]` specifying hours and, optionally, minutes and seconds. (See [this post](https://ruudvanasseldonk.com/2023/01/11/the-yaml-document-from-hell#sexagesimal-numbers) for a discussion on why these values must be quoted.)

When using `start` / `step` / `stop` syntax, the final leadtime is included in verification. That is, the range is inclusive of its upper bound.

Alternatively, the leadtimes to verify may be specified as an arbitrary list of values, e.g.

``` yaml
leadtimes:
  - 03:00:00
  - 06:00:00
  - 09:00:00
```

or

``` yaml
cycles: [3, 6, 9]
```

### meta

The `meta:` block may contain, for example, values tagged with YAML anchors referenced elsewhere via aliases (see the _Aliases_ section [here](https://pyyaml.org/wiki/PyYAMLDocumentation)), or values referenced elsewhere in Jinja2 expressions to be rendered by `uwtools` (see examples in [here](https://uwtools.readthedocs.io/en/stable/sections/user_guide/cli/tools/config.html#realize)).

### projection

The `forecast.projection` value should be a mapping with at least a `proj` key identifying the ID of the [projection](https://proj.org/en/stable/operations/projections/index.html), and potentially additional projection attributes depending on the `proj` value:

  - When `proj` is [`latlon`](https://proj.org/en/stable/operations/conversions/latlon.html), specify no additional attributes.
  - When `proj` is [`lcc`](https://proj.org/en/stable/operations/projections/lcc.html), specify attributes `a`, `b`, `lat_0`, `lat_1`, `lat_2`, and `lon_0`.

### regrid.method

Options are listed [here](https://metplus.readthedocs.io/projects/met/en/main_v11.0/Users_Guide/config_options.html#regrid) (default: `NEAREST`).

### regrid.to

Options are `baseline` and `forecast` (default: `forecast`).

### variables

The `variables:` block is an arbitrarily long mapping from forecast-dataset variable names to generic descriptions of the named variables. Generic-description attributes (names and level types) follow ECMWF conventions: See the [Parameter Database](https://codes.ecmwf.int/grib/param-db/) for names, and [this list](https://codes.ecmwf.int/grib/format/edition-independent/3/) or the output of [`grib_ls`](https://confluence.ecmwf.int/display/ECC/grib_ls) run on a GRIB file containing the variable in question, for level types.

### variables.*.level_type

Currently supported level types are: `atmosphere`, `heightAboveGround`, `isobaricInhPa`, `surface`.

### variables.*.levels

A `levels:` value should only be specified if a level type supports it. Currently, these are: `heightAboveGround`, `isobaricInhPa`.

## Use

```
$ wxvx --help
usage: wxvx -c FILE [-t [TASK]] [-d] [-h] [-k] [-n N] [-s] [-v]

wxvx

Required arguments:
  -c, --config FILE
      Configuration file
  -t, --task [TASK]
      Execute task (no argument => list available tasks)

Optional arguments:
  -d, --debug
      Log all messages
  -h, --help
      Show help and exit
  -k, --check
      Check config and exit
  -n, --threads N
      Number of threads
  -s, --show
      Show a pro-forma config and exit
  -v, --version
      Show version and exit
```

### Example

Consider a `config.yaml`

``` yaml
baseline:
  compare: true
  name: HRRR
  url: https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{{ yyyymmdd }}/conus/hrrr.t{{ hh }}z.wrfprsf{{ "%02d" % fh }}.grib2
cycles:
  start: 2025-03-01T00:00:00
  step: 1
  stop: 2025-03-01T23:00:00
forecast:
  coords:
    latitude: latitude
    level: level
    longitude: longitude
    time:
      inittime: time
      leadtime: lead_time
  mask:
    - [52.61564933, 225.90452027]
    - [52.61564933, 299.08280723]
    - [21.138123,   299.08280723]
    - [21.138123,   225.90452027]
  name: ML
  path: /path/to/forecast.zarr
  projection:
    a: 6371229
    b: 6371229
    lat_0: 38.5
    lat_1: 38.5
    lat_2: 38.5
    lon_0: 262.5
    proj: lcc
leadtimes: [3, 6, 9]
meta:
  grids: "{{ meta.workdir }}/grids"
  levels: &levels [800, 1000]
  workdir: /path/to/workdir
paths:
  grids:
    baseline: "{{ meta.grids }}/baseline"
    forecast: "{{ meta.grids }}/forecast"
  run: "{{ meta.workdir }}/run"
variables:
  HGT:
    level_type: isobaricInhPa
    levels: *levels
    name: gh
  REFC:
    level_type: atmosphere
    name: refc
  T2M:
    level_type: heightAboveGround
    levels: [2]
    name: 2t
```

This config directs `wxvx` to find forecast data, in Zarr format and on a Lambert Conformal grid with the given specification, under `/path/to/forecast.zarr`.

In the forecast dataset, coordinate variables (or attributes) representing latitude, longitude, and vertical level will be named, unsurprisingly, `latitude`, `longitude`, and `level`. Forecast validtime is represented by a combination of initialization time and leadtime, and coordinate variables (or attributes) called `time` and `lead_time`, respectively, provide these values. (Alternatively, a forecast dataset might provide validtime instead of leadtime, with the `wxvx` YAML key `validtime` used instead of `leadtime`.)

Verification will be limited to points within the bounding box given by `mask`.

The forecast will be called `ML` in MET `.stat` files and in plots.

It will be verified against `HRRR` analysis, which can be found in GRIB files located either remotely (e.g. in an AWS bucket) or locally (via `file://` URLs or plain filesystem paths), given as the `baseline.url` value, where `yyyymmdd`, `hh`, and `fh` will be filled in by `wxvx`. (The `yyyymmdd` and `hh` values are strings like `20250523` and `06`, while `fh` is an `int` value to be formatted as needed.)

24 1-hourly cycles starting at 2025-03-01 00Z, each with forecast leadtimes 3, 6, and 9, will be verified.

Variable grids extracted from baseline datasets will be written to `/path/to/workdir/baseline`, forecast dataset to `/path/to/workdir/forecast`, and run output to `/path/to/workdir/run`. The [Jinja2](https://jinja.palletsprojects.com/en/stable/) expressions inside `{{ }}` markers will be processed by [`uwtools`](https://uwtools.readthedocs.io/en/stable/) and may use any features it supports.

Three variables -- geopotential height, composite reflectivity, and 2-meter temperature, will be verified. The keys under `variables` map the names of the variables as they appear in the forecast dataset to a canonical description of the variable using ECMWF variable names and level-type descriptions (see the notes in the _Configuration_ section for links). (Note that some variables do not support a "level" concept.) The full verification task-graph will comprise: cycles x leadtimes x variables x levels.

Invoking `wxvx -c config.yaml -t grids_baseline` would stage the baseline grids to disk, only; `-t grids_forecast` would stage the forecast grids; `-t grids` would stage both. Specifying `-t stats` would produce statistics via MET tools, but also stage grids if they are not already available, since the grids are required by the MET processes. Specifying `-t plots` would plot statistics, but also _produce_ statistics (and stage grids) if they are not already available.

## Miscellaneous

### CF Metadata

When `wxvx` extracts grids from the forecast dataset and writes them to netCDF files to be processed by MET, it decorates them with certain [CF Metadata](https://cfconventions.org/) as [required by MET](https://metplus.readthedocs.io/projects/met/en/main_v11.0/Users_Guide/data_io.html#requirements-for-cf-compliant-netcdf). See [this database](https://cfconventions.org/Data/cf-standard-names/current/build/cf-standard-name-table.html) for CF standard names and units.

## Development

1. In the `base` environment of a [Miniforge](https://github.com/conda-forge/miniforge) installation, install the [`condev`](https://github.com/maddenp/condev) package. (Add the flags `-c conda-forge --override-channels` to the `conda create` command if using a non-conda-forge conda installation.)

``` bash
conda install -y -c maddenp condev
```

2. In the root directory of a `wxvx` git clone:

``` bash
make devshell
```

This will create and activate a conda virtual environment named `DEV-wxvx`, where all build, run, and test requirement packages are available, and the code under `src/wxvx/` is live-linked into the environment, such that code changes are immediately live and testable. Several `make` targets are available: `make format` formats Python code and JSON documents, and `make test` runs all code-quality checks (equivalent to `make lint && make typecheck && make unittest`, targets which can also be run independently). A common development idiom is to periodically run `make format && make test`.

When you are finished, type `exit` to return to your previous shell. The `DEV-wxvx` environment will still exist, and a future `make devshell` command will more-or-less instantly activate it again.

## Cookbook

### Extract Grid Projection from GRIB

``` python
conda install -y pygrib
python -c "import pygrib; print(pygrib.open('a.grib2').message(1).projparams)"
```
