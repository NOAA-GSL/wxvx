"""
Tests for wxvx.net.
"""

from contextlib import contextmanager
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
    @contextmanager
    def get(url, **kwargs):
        assert url == URL
        assert kwargs == dict(
            allow_redirects=True, stream=True, timeout=net.TIMEOUT, headers=headers
        )
        response = Mock(
            iter_content=Mock(return_value=iter([bytes(out, encoding="utf-8")])),
            status_code=code,
        )
        yield response

    session = Mock(get=get)
    headers = {"Range": "bytes=1-2"} if byterange else {}
    path = Path(fs.create_file("f").path)
    with patch.dict(net.NET, {"session": session}):
        assert net.fetch(taskname="task", url=URL, path=path, headers=headers) is ret
    assert path.read_text(encoding="utf-8") == out
    assert logged(f"Could not fetch {URL}" if code == 404 else f"Wrote {path}")


def test_net_status():
    code = 42
    response = Mock(status_code=code)
    session = Mock(get=Mock(return_value=response), head=Mock(return_value=response))
    with patch.dict(net.NET, {"session": session}):
        assert net.status(url=URL) == code
    session.head.assert_called_once_with(URL, timeout=net.TIMEOUT)
