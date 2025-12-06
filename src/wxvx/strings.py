from dataclasses import dataclass


@dataclass(frozen=True)
class S:
    GFS: str = "GFS"
    HRRR: str = "HRRR"
    OBS: str = "OBS"
    PREPBUFR: str = "PREPBUFR"
    baseline: str = "baseline"
    cycles: str = "cycles"
    forecast: str = "forecast"
    grids: str = "grids"
    leadtimes: str = "leadtimes"
    obs: str = "obs"
    paths: str = "paths"
    properties: str = "properties"
    run: str = "run"
    session: str = "session"
    truth: str = "truth"
    variables: str = "variables"
    name: str = "name"
    type: str = "type"
    coords: str = "coords"
    time: str = "time"
