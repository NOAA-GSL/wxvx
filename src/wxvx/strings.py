from dataclasses import dataclass


@dataclass(frozen=True)
class STR:
    BASELINE: str = "BASELINE"
    FORECAST: str = "FORECAST"
    GFS: str = "GFS"
    HRRR: str = "HRRR"
    PREPBUFR: str = "PREPBUFR"
    TRUTH: str = "TRUTH"
    session: str = "session"
