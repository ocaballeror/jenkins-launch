import sys

import pytest

from launch_jenkins import launch_jenkins
from launch_jenkins import HTTPError
from launch_jenkins import CaseInsensitiveDict


class FakeResponse:
    def __init__(self, text='', headers=None, status_code=200):
        self.text = text
        self._readable = text
        self.headers = CaseInsensitiveDict(headers)
        if sys.version_info >= (3,):
            self.headers._headers = self.headers
        else:
            self.headers.dict = self.headers
        self.status_code = status_code

    def __iter__(self):
        while True:
            self.text = self.read(8192)
            if self.text:
                yield self
            else:
                break

    def read(self, size=0):
        if not size:
            size = len(self._readable)
        text = self._readable[:size]
        self._readable = self._readable[size:]
        if not isinstance(text, bytes):
            text = text.encode('utf-8')
        return text


@pytest.fixture
def config():
    backup = launch_jenkins.CONFIG.copy()
    try:
        yield
    finally:
        launch_jenkins.CONFIG = backup


@pytest.fixture
def mock_url(monkeypatch):
    def ret(mock_pairs):
        if not isinstance(mock_pairs, list):
            mock_pairs = [mock_pairs]
        mock_pairs = {p.pop('url'): p for p in mock_pairs}
        _get_url = launch_jenkins.get_url

        def mock(url, *args, **kwargs):
            resp = mock_pairs.get(url, None)
            if not resp:
                return _get_url(url, *args, **kwargs)

            resp['text'] = resp.get('text', '')
            resp['headers'] = resp.get('headers', {})
            resp['status_code'] = resp.get('status_code', 200)
            if resp['status_code'] >= 400:
                raise HTTPError(
                    url,
                    resp['status_code'],
                    resp['text'],
                    resp['headers'],
                    None,
                )
            return FakeResponse(**resp)

        monkeypatch.setattr(launch_jenkins, 'get_url', mock)

    return ret