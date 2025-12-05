from dataclasses import dataclass


@dataclass(frozen=True)
class STR:
    GFS: str = "GFS"
    HRRR: str = "HRRR"
    PREPBUFR: str = "PREPBUFR"
    OBS: str = "OBS"
    session: str = "session"
    truth: str = "truth"
