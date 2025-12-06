from dataclasses import dataclass


@dataclass(frozen=True)
class S:
    GFS: str = "GFS"
    HRRR: str = "HRRR"
    OBS: str = "OBS"
    PREPBUFR: str = "PREPBUFR"
    baseline: str = "baseline"
    coords: str = "coords"
    cycles: str = "cycles"
    forecast: str = "forecast"
    grids: str = "grids"
    leadtimes: str = "leadtimes"
    name: str = "name"
    obs: str = "obs"
    paths: str = "paths"
    properties: str = "properties"
    run: str = "run"
    session: str = "session"
    time: str = "time"
    truth: str = "truth"
    type: str = "type"
    variables: str = "variables"
    level: str = "level"
    level_type: str = "level_type"
    levels: str = "levels"
    url: str = "url"
