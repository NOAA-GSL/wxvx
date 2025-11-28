from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from requests.adapters import HTTPAdapter

from wxvx.util import atomic

if TYPE_CHECKING:
    from pathlib import Path

from requests import Session

# The session needs to be set up, by calling configure_session(),  before fetch() or status() are
# called. The connections argument should be equal to the number of threads in use, so the configure
# call is made from wxvx.cli.main() where this is known.

_STATE: dict = {}

# Use a lower connect timeout to avoid wasted time when running (possibly accidentally) on a system,
# like an HPC compute node, without internet access. The client will wait this many seconds for the
# remote host to respond to a connection request before giving up. Specify a higher read timeout to
# accommodate remote hosts already connected that may just be temporarily unable to respond, maybe
# due to transient network issues.

TIMEOUT = (5, 30)  # (connect, read)


def fetch(taskname: str, url: str, path: Path, headers: dict[str, str] | None = None) -> bool:
    suffix = " %s" % headers.get("Range", "") if headers else ""
    logging.info("%s: Fetching %s%s", taskname, url, suffix)
    kwargs = dict(allow_redirects=True, stream=True, timeout=TIMEOUT, headers=headers or {})
    with _STATE["session"].get(url, **kwargs) as response:
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


def configure_session(connections: int) -> None:
    session = Session()
    adapter = HTTPAdapter(pool_connections=connections, pool_maxsize=connections)
    for scheme in ["http://", "https://"]:
        session.mount(scheme, adapter)
    _STATE["session"] = session


def status(url: str) -> int:
    session: Session = _STATE["session"]
    return session.head(url, timeout=TIMEOUT).status_code
