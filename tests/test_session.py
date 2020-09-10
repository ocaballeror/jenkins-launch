import pytest

from launch_jenkins import Session
from launch_jenkins import HTTPError

from .conftest import g_auth, g_auth_b64, g_url


def test_base(monkeypatch):
    """
    Check that the `.base` attribute is auto populated with the base URL of the
    given server when we initialize a new Session.
    """
    monkeypatch.setattr(Session, '_get_crumb', lambda self: None)
    session = Session('https://example.com:8443/some/path')
    assert session.base == 'https://example.com:8443'


def test_auth_header(monkeypatch):
    """
    Check that the Authorization header is auto populated when we pass
    credentials to a new Session.
    """
    monkeypatch.setattr(Session, '_get_crumb', lambda self: None)
    session = Session('https://example.com:8443/some/path', auth=g_auth)
    assert session.headers['Authorization'] == g_auth_b64


def test_crumb_header(mock_url):
    """
    Check that creating a new Session correctly auto populates its jenkins
    crumb header.
    """
    base = '/'.join(g_url.split('/')[:3])
    mock_url({'url': base + '/crumbIssuer/api/xml', 'text': 'key:value'})
    session = Session(g_url)
    assert session.headers['key'] == 'value'


def test_crumb_httperror(mock_url, session):
    """
    Check that Session._get_crumb ignores HTTP errors only if they are 404.
    """
    headers = session.headers.copy()
    base = '/'.join(g_url.split('/')[:3])
    mock_url({'url': base + '/crumbIssuer/api/xml', 'status_code': 404})
    session._get_crumb()
    # response was 404 so nothing happened
    assert session.headers == headers

    mock_url({'url': base + '/crumbIssuer/api/xml', 'status_code': 500})
    # if response was anything other than 404 the error is propagated
    with pytest.raises(HTTPError):
        session._get_crumb()
