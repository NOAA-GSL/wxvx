from dataclasses import dataclass


@dataclass(frozen=True)
class STR:
    GFS: str = "GFS"
    HRRR: str = "HRRR"
    PREPBUFR: str = "PREPBUFR"
    OBS: str = "OBS"
    session: str = "session"
    truth: str = "truth"
    forecast: str = "forecast"
    baseline: str = "baseline"
    obs: str = "obs"
    run: str = "run"
    paths: str = "paths"
    grids: str = "grids"
