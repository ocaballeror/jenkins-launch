from launch_jenkins import Session

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
