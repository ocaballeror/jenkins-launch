import os
import sys
from collections import namedtuple

import pytest

from launch_jenkins import launch_jenkins
from launch_jenkins import HTTPError
from launch_jenkins import CaseInsensitiveDict
from launch_jenkins import Session


g_url = "http://example.com/job/thing/job/other/job/master"
g_auth = ('user', 'pwd')
g_auth_b64 = 'Basic dXNlcjpwd2Q='
g_params = ['-j', g_url, '-u', g_auth[0], '-t', g_auth[1]]


class Dummy:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeResponse:
    """
    Mock response class that works more or less like an HTTP Response object.
    """

    def __init__(self, text='', headers=None, status_code=200):
        self.info = lambda: Dummy(
            get_all=lambda a, b=None: b,
            getheaders=lambda a: None
        )
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
    """
    Fixture to restore the original CONFIG in the launch_jenkins module.
    """
    backup = launch_jenkins.CONFIG.copy()
    try:
        yield
    finally:
        launch_jenkins.CONFIG = backup


@pytest.fixture(scope='session')
def session():
    return Session(g_url, g_auth)


@pytest.fixture(scope='function')
def unparametrized(monkeypatch, session):
    monkeypatch.setattr(session, 'get_job_params', lambda a: {})


@pytest.fixture
def mock_url(monkeypatch):
    """
    Returns a function that allows you to return a canned FakeResponse when a
    specific url is requested.
    """

    def ret(mock_pairs):
        if not isinstance(mock_pairs, list):
            mock_pairs = [mock_pairs]
        mock_pairs = {
            (p.pop('url').split('?')[0], p.pop('method', 'GET').upper()): p
            for p in mock_pairs
        }

        def mock(request, *args, **kwargs):
            url = request.get_full_url().split('?')[0]
            method = request.get_method()
            resp = mock_pairs.get((url, method), None)
            if resp is None:
                raise RuntimeError(
                    "No mock response set for {} '{}'".format(method, url)
                )

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

        monkeypatch.setattr(launch_jenkins, 'urlopen', mock)

    return ret


@pytest.fixture(scope='function')
def terminal_size(monkeypatch):
    """
    Set a fake os.get_terminal_size() function that returns (30, 30).
    """

    def fake_terminal_size(*args, **kwargs):
        return Size(30, 30)

    Size = namedtuple('terminal_size', 'columns lines')
    has_func = hasattr(os, 'get_terminal_size')
    if not has_func:
        os.get_terminal_size = fake_terminal_size
    else:
        monkeypatch.setattr(os, 'get_terminal_size', fake_terminal_size)
    yield

    if not has_func:
        del os.get_terminal_size


@pytest.fixture(scope='function')
def tty(monkeypatch, terminal_size):
    """
    Set up environment so it looks like a valid TTY.
    """
    monkeypatch.setattr(launch_jenkins, 'is_progressbar_capable', lambda: True)
