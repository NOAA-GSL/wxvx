from dataclasses import dataclass

# This module provides containers for string literals used throughout the codebase, organized by
# the source of their definition. Most values are dynamically set to match the key, but explicit
# values can also be provided when the key and value should not be the same. This mechanism reduces
# the risk of typos in string literals, and exposes references to the type checker for validation.

# ruff: noqa: N815

# Private

_ = ""  # default value, to be replaced by key


class _ValsMatchKeys:
    def __post_init__(self):
        attr = "__dataclass_fields__"
        fields = getattr(self, attr).values()
        for field in fields:
            if not getattr(self, field.name):
                object.__setattr__(self, field.name, field.name)


@dataclass(frozen=True)
class _EC(_ValsMatchKeys):
    """
    Strings defined by ECMWF / ecCodes.
    """

    gh: str = _
    q: str = _
    refc: str = _
    sp: str = _
    t2: str = "2t"
    t: str = _
    u: str = _
    u_10m: str = _
    v: str = _
    v_10m: str = _
    w: str = _


@dataclass(frozen=True)
class _MET(_ValsMatchKeys):
    """
    Strings defined by MET.
    """

    ATM: str = _
    BILIN: str = _
    BOTH: str = _
    CIRCLE: str = _
    FALSE: str = _
    FCST_LEAD: str = _
    FCST_THRESH: str = _
    FSS: str = _
    FULL: str = _
    INTERP_PNTS: str = _
    LABEL: str = _
    ME: str = _
    MODEL: str = _
    NEAREST: str = _
    PODY: str = _
    RMSE: str = _
    SFC: str = _
    SQUARE: str = _
    beg: str = _
    cat_thresh: str = _
    climo: str = _
    cnt: str = _
    cnt_thresh: str = _
    cts: str = _
    end: str = _
    fcst: str = _
    field: str = _
    grid: str = _
    interp: str = _
    level: str = _
    mask: str = _
    message_type: str = _
    message_type_group_map: str = _
    method: str = _
    model: str = _
    name: str = _
    nbrcnt: str = _
    nbrhd: str = _
    nbrhd_shape: str = _
    nbrhd_width: str = _
    nc_pairs_flag: str = _
    obs: str = _
    obs_bufr_var: str = _
    obs_var: str = _
    obs_window: str = _
    obtype: str = _
    output_flag: str = _
    output_prefix: str = _
    poly: str = _
    quality_mark_thresh: str = _
    raw: str = _
    regrid: str = _
    set_attr_level: str = _
    shape: str = _
    step: str = _
    time_summary: str = _
    tmp_dir: str = _
    to_grid: str = _
    type: str = _
    vld_thresh: str = _
    width: str = _


@dataclass(frozen=True)
class _NOAA(_ValsMatchKeys):
    """
    Strings defined by NOAA.
    """

    HGT: str = _
    PRES: str = _
    REFC: str = _
    SPFH: str = _
    T2M: str = _
    TMP: str = _
    UGRD: str = _
    VGRD: str = _
    VVEL: str = _


@dataclass(frozen=True)
class _S(_ValsMatchKeys):
    """
    Strings defined by wxvx, plus strings from various other sources.
    """

    GFS: str = _
    HRRR: str = _
    OBS: str = _
    PREPBUFR: str = _
    atmosphere: str = _
    baseline: str = _
    coords: str = _
    cycle: str = _
    cycles: str = _
    env: str = _
    fh: str = _
    firstbyte: str = _
    forecast: str = _
    forecast_reference_time: str = _
    format: str = _
    grid: str = _
    grids: str = _
    grids_baseline: str = _
    grids_forecast: str = _
    grids_truth: str = _
    heightAboveGround: str = _
    hh: str = _
    inittime: str = _
    isobaricInhPa: str = _
    lastbyte: str = _
    latitude: str = _
    latlon: str = _
    leadtime: str = _
    leadtimes: str = _
    level: str = _
    level_type: str = _
    levels: str = _
    longitude: str = _
    mask: str = _
    method: str = _
    name: str = _
    ncdiffs: str = _
    obs: str = _
    path: str = _
    paths: str = _
    plots: str = _
    point: str = _
    pool: str = _
    proj: str = _
    projection: str = _
    properties: str = _
    regrid: str = _
    run: str = _
    session: str = _
    shortName: str = _
    start: str = _
    stats: str = _
    step: str = _
    stop: str = _
    surface: str = _
    time: str = _
    to: str = _
    truth: str = _
    type: str = _
    typeOfLevel: str = _
    url: str = _
    validtime: str = _
    variables: str = _
    yyyymmdd: str = _


# Public

EC = _EC()
MET = _MET()
NOAA = _NOAA()
S = _S()
