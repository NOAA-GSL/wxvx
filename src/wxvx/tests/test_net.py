"""
Tests for wxvx.net.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from pytest import mark

from wxvx import net

URL = "https://some.url"

# Tests


@mark.parametrize(
    ("code", "out", "byterange", "ret"),
    [(200, "foo", False, True), (206, "foo", True, True), (404, "", False, False)],
)
def test_net_fetch__fail(byterange, code, fs, logged, out, ret):
    response = Mock()
    response.status_code = code
    response.iter_content.return_value = iter([bytes(out, encoding="utf-8")])
    headers = {"Range": "bytes=1-2"} if byterange else {}
    path = Path(fs.create_file("f").path)
    with patch.object(net, "session") as session:
        session().get.return_value = response
        assert net.fetch(taskname="task", url=URL, path=path, headers=headers) is ret
    session().get.assert_called_once_with(
        URL, allow_redirects=True, stream=True, timeout=net.TIMEOUT, headers=headers
    )
    assert path.read_text(encoding="utf-8") == out
    assert logged(f"Could not fetch {URL}" if code == 404 else f"Wrote {path}")


def test_net_status():
    code = 42
    response = Mock()
    response.status_code = code
    with patch.object(net, "session") as session:
        session().head.return_value = response
        assert net.status(url=URL) == code
    session().head.assert_called_once_with(URL, timeout=net.TIMEOUT)
