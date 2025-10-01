from __future__ import annotations

import logging
from functools import cache
from http import HTTPStatus
from typing import TYPE_CHECKING

from wxvx.util import atomic

if TYPE_CHECKING:
    from pathlib import Path

from requests import Session

TIMEOUT = (5, 30)  # (connect_timeout, read_timeout)


def fetch(taskname: str, url: str, path: Path, headers: dict[str, str] | None = None) -> bool:
    suffix = " %s" % headers.get("Range", "") if headers else ""
    logging.info("%s: Fetching %s%s", taskname, url, suffix)
    response = session().get(
        url, allow_redirects=True, stream=True, timeout=TIMEOUT, headers=headers or {}
    )
    expected = HTTPStatus.PARTIAL_CONTENT if headers and "Range" in headers else HTTPStatus.OK
    if response.status_code == expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        with atomic(path) as tmp, tmp.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info("%s: Wrote %s", taskname, path)
        return True
    logging.warning("%s: Could not fetch %s", taskname, url)
    return False


@cache
def session() -> Session:
    return Session()


def status(url: str) -> int:
    return session().head(url, timeout=TIMEOUT).status_code
