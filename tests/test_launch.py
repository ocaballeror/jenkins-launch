from __future__ import unicode_literals

import os
import sys
import json
import time
import ssl
from io import StringIO
from threading import Thread

import pytest

if sys.version_info >= (3,):
    from urllib.parse import parse_qs
else:
    from urlparse import parse_qs

    range = xrange  # noqa:F821


from launch_jenkins import launch_jenkins
from launch_jenkins import parse_job_url
from launch_jenkins import get_stderr_size_unix
from launch_jenkins import is_progressbar_capable
from launch_jenkins import init_ssl
from launch_jenkins import Session
from launch_jenkins import launch_build
from launch_jenkins import wait_queue
from launch_jenkins import wait_job
from launch_jenkins import dump_log
from launch_jenkins import HTTPError

from .conftest import FakeResponse
from .conftest import g_url, g_auth, g_auth_b64
from .test_helper import assert_show_empty_progress
from .test_helper import assert_show_no_progressbar
from .test_helper import assert_show_progressbar
from .test_helper import assert_show_progressbar_millis
from .test_helper import assert_progressbar_millis
from .test_helper import raise_error


@pytest.mark.parametrize(
    'response',
    [
        {},
        {'key': 'value'},
        {'property': []},
        {'property': [{'key': 'value'}]},
        {'property': [{'parameterDefinitions': ['things']}]},
        {
            'property': [
                {
                    '_class': 'hudson.model.ParametersDefinitionProperty',
                    'parameterDefinitions': [],
                }
            ]
        },
    ],
)
def test_get_job_params_empty(mock_url, response, session):
    """
    Get job params when there is no parameter definition
    """
    mock_url({'url': g_url + '/api/json', 'text': json.dumps(response)})
    assert session.get_job_params(g_url) == {}


@pytest.mark.parametrize(
    'response, expect',
    [
        (
            [
                {
                    "_class": "hudson.model.ChoiceParameterDefinition",
                    "defaultParameterValue": {
                        "_class": "hudson.model.StringParameterValue",
                        "name": "action",
                        "value": "create or update",
                    },
                    "description": "Action to be executed",
                    "name": "action",
                    "type": "ChoiceParameterDefinition",
                    "choices": ["create or update", "run discovery"],
                },
                {
                    "_class": "hudson.model.StringParameterDefinition",
                    "defaultParameterValue": {
                        "_class": "hudson.model.StringParameterValue",
                        "name": "ci_name",
                        "value": "",
                    },
                    "description": "CI name",
                    "name": "ci_name",
                    "type": "StringParameterDefinition",
                },
            ],
            {'action': ['create or update', 'run discovery'], 'ci_name': None},
        )
    ],
)
def test_get_job_params(mock_url, session, response, expect):
    response = {
        'property': [
            {
                '_class': 'hudson.model.ParametersDefinitionProperty',
                'parameterDefinitions': response,
            }
        ]
    }
    mock_url({'url': g_url + '/api/json', 'text': json.dumps(response)})
    assert session.get_job_params(g_url) == expect


@pytest.mark.parametrize(
    'definitions,supplied',
    [
        ({}, {'a': 'b'}),
        ({'a': None}, {'b': 'c'}),
        ({'a': None}, {'a': 'b', 'c': 'd'}),
        ({'a': ['b', 'c']}, {'a': 'd'}),
    ],
    ids=[
        'supplied, no definitions',
        'nonexistent',
        'some exist, others not',
        'invalid choice',
    ],
)
def test_validate_params_error(definitions, supplied):
    with pytest.raises(ValueError):
        launch_jenkins.validate_params(definitions, supplied)


@pytest.mark.parametrize(
    'definitions,supplied',
    [
        ({'param': ['a', 'b'], 'other': None}, {}),
        ({'param': ['a', 'b'], 'other': None}, {'param': 'b'}),
        ({'param': ['a', 'b'], 'other': None}, {'other': 'value here'}),
        (
            {'param': ['a', 'b'], 'other': None},
            {'param': 'b', 'other': 'asdfasdf'},
        ),
    ],
    ids=[
        'nothing supplied',
        'supplied choice',
        'supplied string',
        'supplied both',
    ],
)
def test_validate_params_ok(definitions, supplied):
    launch_jenkins.validate_params(definitions, supplied)


@pytest.mark.parametrize(
    'url', ['http', 'http://example.com/', 'http://example.com/job/']
)
def test_parse_build_url_error(url):
    """
    Check for a ValueError when trying to parse a build url but a malformed one
    is given.
    """
    with pytest.raises(ValueError) as error:
        parse_job_url(g_url + url, True)
        assert 'invalid url' in str(error.value).lower()


@pytest.mark.parametrize(
    'url',
    [
        g_url,
        g_url + '/build',
        g_url + '/notanumber',
        g_url + '/1isnot0',
        g_url + 'lastbuild',
    ],
)
def test_parse_build_url_missing_number(url):
    """
    Check for a ValueError when trying to parse a build url, but the build
    number is missing.
    """
    with pytest.raises(ValueError) as error:
        parse_job_url(g_url + url, True)
        assert 'make sure there is a build number' in str(error.value).lower()


@pytest.mark.parametrize('url', ['/53', '/lastBuild'])
def test_parse_build_url(url):
    """
    Test parsing build urls with a build number at the end.
    """
    url = g_url + url
    assert parse_job_url(url, True) == url


@pytest.mark.parametrize(
    'url',
    [
        g_url,
        g_url + '/',
        g_url + '/build',
        g_url + '/build/',
        g_url + '/buildWithParameters',
        g_url + '/buildWithParameters/',
    ],
)
def test_parse_job_url(url):
    assert parse_job_url(url) == g_url


@pytest.mark.parametrize(
    'job_url',
    [
        'http',
        'http/job/something',
        'http://example.com/',
        'http://example.com/job/',
        'http://example.com/job/a/b/',
        g_url + '/BUILD',
        g_url + '/buildWithParameters?a=b',
        g_url + '/42',
        g_url + '/lastBuild',
    ],
    ids=[
        'not a url',
        'not a url, but ends in /job',
        'no /job',
        'cannot end in /job',
        'penultimate section should be /job/',
        '/build should be lowercase',
        'no parameters allowed in url',
        'unexpected job number',
        'unexpected lastBuild',
    ],
)
def test_parse_job_url_error(job_url):
    with pytest.raises(ValueError) as error:
        parse_job_url(job_url)
    assert 'invalid job url' in str(error.value).lower()


def test_get_url(monkeypatch, session):
    requests = []
    text = 'hello world'
    resp_headers = dict(location='here')
    url = 'http://example.com'

    def fake_response(r, *args, **kwargs):
        requests.append(r)
        return FakeResponse(text, headers=resp_headers)

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    resp = session.get_url(url)
    assert resp.text == text
    assert resp.headers['location'] == 'here'
    assert resp.headers['LoCaTiOn'] == 'here'

    req = requests[0]
    print(req)
    print(req.__dict__)
    if hasattr(req, '_Request__original'):
        assert req._Request__original == url
    else:
        assert req._full_url == url
    assert req.data is None
    assert req.headers['Authorization'] == g_auth_b64


def test_get_url_escaped(mock_url, session):
    text = 'yes'
    url = 'http://example.com/feature%252Fhelloworld'
    mock_url(dict(url=url, text=text))

    assert session.get_url(url).text == text


def test_get_url_data(monkeypatch, session):
    requests = []
    url = 'http://example.com'
    data = {'simple': 'hello', 'space': 'hello world', 'weird': 'jk34$"/ &aks'}

    def fake_response(r, *args, **kwargs):
        requests.append(r)
        return FakeResponse()

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    session.get_url(url, data=data)

    req = requests[0]
    if hasattr(req, '_Request__original'):
        assert req._Request__original == url
    else:
        assert req._full_url == url
    assert req.headers['Authorization'] == g_auth_b64
    assert req.headers['Content-type'] == 'application/x-www-form-urlencoded'
    parsed = parse_qs(req.data.decode('utf-8'))
    parsed = {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
    assert parsed == data


def test_get_url_stream(monkeypatch, session):
    requests = []
    text = 'a' * 8192 + 'b' * 100
    url = 'http://example.com'

    def fake_response(r, *args, **kwargs):
        requests.append(r)
        return FakeResponse(text)

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    resp = session.get_url(url, stream=True)
    assert not hasattr(resp, 'text')
    assert next(resp).text.decode('utf-8') == 'a' * 8192
    assert next(resp).text.decode('utf-8') == 'b' * 100
    with pytest.raises(StopIteration):
        next(resp)


def test_get_url_ssl(monkeypatch, tmp_path, mock_url, session):
    url = 'https://example.com/'
    monkeypatch.setitem(launch_jenkins.CONFIG, 'verify_ssl', True)

    # sabotage system certs so that verification fails
    file = tmp_path / 'cert'
    file.touch()
    monkeypatch.setitem(os.environ, 'SSL_CERT_FILE', str(file))
    monkeypatch.setitem(os.environ, 'SSL_CERT_DIR', str(tmp_path))

    with pytest.raises(ssl.SSLError):
        # This should fail
        monkeypatch.setattr(session, 'context', init_ssl())

    # disable ssl verifying and check that it doesn't fail this time
    monkeypatch.setitem(launch_jenkins.CONFIG, 'verify_ssl', False)
    monkeypatch.setattr(session, 'context', init_ssl())
    assert session.get_url(url)


def test_get_url_retry(monkeypatch, session):
    url = 'https://example.com/'

    def raise_httperror(*args, **kwargs):
        raise HTTPError(url, 500, 'Internal Server Error', {}, None)

    def undo_and_raise(*args, **kwargs):
        monkeypatch.undo()
        raise HTTPError(url, 500, 'Internal Server Error', {}, None)

    # raise an error every time
    monkeypatch.setattr(launch_jenkins, 'urlopen', raise_httperror)
    with pytest.raises(HTTPError):
        session.get_url(url, retries=5)

    # raise an error the first time and succeed the second
    monkeypatch.setattr(launch_jenkins, 'urlopen', undo_and_raise)
    assert session.get_url(url, retries=2)

    # no retries for posts
    monkeypatch.setattr(launch_jenkins, 'urlopen', undo_and_raise)
    with pytest.raises(HTTPError):
        session.get_url(url, data={'hello': 'world'}, retries=2)


def test_build_no_params(mock_url, unparametrized, session):
    headers = {'Location': 'some queue'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))

    # Launch build
    assert session.launch_build(g_url, {}) == 'some queue'


def test_build_with_params(mock_url, monkeypatch, session):
    headers = {'Location': 'param queue'}

    # Set build properties as parametrized
    def mock_get_job_params(*args):
        return {'param': None}

    monkeypatch.setattr(session, 'get_job_params', mock_get_job_params)

    mock_url(
        dict(
            url=g_url + '/buildWithParameters', headers=headers, method='POST'
        )
    )

    # Launch parametrized build
    assert session.launch_build(g_url) == 'param queue'
    assert session.launch_build(g_url) == 'param queue'


def test_launch_error(mock_url, unparametrized, session):
    mock_url(dict(url=g_url + '/build', status_code=400, method='POST'))

    with pytest.raises(HTTPError):
        session.launch_build(g_url)


def test_launch_error_no_queue(mock_url, unparametrized, session):
    headers = {'Header': 'value'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))

    # Response has no location header
    with pytest.raises(AssertionError):
        session.launch_build(g_url, {})

    headers = {'Location': 'this is not the word you are looking for'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))
    # Location has no queue url
    with pytest.raises(AssertionError):
        session.launch_build(g_url, {})


def test_wait_queue(mock_url, session):
    def set_finished():
        time.sleep(0.5)
        resp = {'executable': {'url': 'some url'}}
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/api/json', text=resp))

    mock_url(dict(url=g_url + '/api/json', text='{}'))
    Thread(target=set_finished).start()

    t0 = time.time()
    session.wait_queue(g_url, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_queue_cancelled(mock_url, session):
    def set_finished():
        time.sleep(0.5)
        resp = {'cancelled': True}
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/api/json', text=resp))

    mock_url(dict(url=g_url + '/api/json', text='{}'))
    Thread(target=set_finished).start()

    t0 = time.time()
    with pytest.raises(RuntimeError):
        session.wait_queue(g_url, 0.2)
    assert time.time() - t0 >= 0.5


@pytest.mark.parametrize(
    'status, expect',
    [
        ('SUCCESS', True),
        ('FAILED', False),
        ('CANCELLED', False),
        ('IN_PROGRESS', None),
    ],
)
def test_get_job_status(mock_url, status, expect, session):
    stage = {'name': 'stage', 'status': status}
    resp = {'name': 'name', 'status': status, 'stages': [stage]}
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    assert session.get_job_status(g_url) == (expect, stage)


@pytest.mark.parametrize('duration, status, stage', [
    (None, None, {}),
    (0, None, {}),
    (10, False, {}),
])
def test_get_job_status_not_executed(
    duration, status, stage, mock_url, session
):
    """
    Test get_job_status when the status is NOT_EXECUTED.

    It should report that the job is building if durationMillis is 0 or absent,
    and failure if it's something else.
    """
    resp = {'status': 'NOT_EXECUTED'}
    if duration is not None:
        resp['durationMillis'] = duration

    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    assert session.get_job_status(g_url) == (status, stage)


def test_get_job_status_in_progress(mock_url, session):
    """
    Check that get_job_status returns the current running stage when the build
    is in progress.
    """
    current = {'name': 'stage2', 'status': 'IN_PROGRESS'}
    stages = [
        {'name': 'stage0', 'status': 'SUCCESS'},
        {'name': 'stage1', 'status': 'NOT_EXECUTED'},
        current,
        {'name': 'stage3', 'status': 'NOT_EXECUTED'},
    ]
    resp = {'name': 'name', 'status': 'IN_PROGRESS', 'stages': stages}
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    assert session.get_job_status(g_url) == (None, current)


def test_get_job_status_false_negative(mock_url, session):
    """
    Test that we read the correct response from the list of stages when Jenkins
    reports a false negative in the status header.
    """
    last = {'name': 'stage4', 'status': 'SUCCESS'}
    stages = [
        {'name': 'stage0', 'status': 'SUCCESS'},
        {'name': 'stage1', 'status': 'SUCCESS'},
        {'name': 'stage2', 'status': 'NOT_EXECUTED'},
        last,
    ]
    resp = {'name': 'name', 'status': 'FAILED', 'stages': stages}
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    assert session.get_job_status(g_url) == (True, last)


@pytest.mark.parametrize(
    'status, success',
    [('SUCCESS', True), ('FAILED', False), ('CANCELLED', False)],
)
def test_wait_job(mock_url, status, success, session):
    """
    Check that wait_job returns True or False when a build reaches a final
    status.
    """

    def set_finished():
        time.sleep(0.5)
        resp = {
            'status': status,
            'name': 'name',
            'stages': [{'status': status, 'name': 'stage'}],
        }
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/wfapi/describe', text=resp))

    resp = {
        'name': 'name',
        'status': 'IN_PROGRESS',
        'stages': [{'name': 'stage', 'status': 'IN_PROGRESS'}],
    }
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    Thread(target=set_finished).start()

    t0 = time.time()
    assert session.wait_job(g_url, 0.2) == success
    assert time.time() - t0 >= 0.5


def test_wait_job_nonexistent(monkeypatch, session):
    status_code = 400
    build_number = 65
    build_url = 'http://example.com/%s' % build_number

    def raise_httperror(*args, **kwargs):
        raise HTTPError(build_url, status_code, 'Mock http error', {}, None)

    monkeypatch.setattr(session, 'get_url', raise_httperror)
    with pytest.raises(HTTPError) as error:
        session.wait_job(build_url)
        assert str(error.value) == 'Mock http error'

    status_code = 404
    with pytest.raises(HTTPError) as error:
        session.wait_job(build_url)
        assert str(error.value) == 'Build #%s does not exist' % build_number


def test_wait_job_get_duration(mock_url, capsys, tty, session):
    """
    Return the list of stages and assert that wait_job can find the current one
    and extract its duration.
    """

    def set_finished():
        time.sleep(0.5)
        resp = {
            'status': 'SUCCESS',
            'name': 'name',
            'stages': [{'name': 'stage', 'status': 'SUCCESS'}],
        }
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/wfapi/describe', text=resp))

    durationMillis = 1200
    resp = {
        'name': 'name',
        'status': 'IN_PROGRESS',
        'stages': [
            {'name': 'stage1', 'status': 'SUCCESS'},
            {'name': 'stage2', 'status': 'SUCCESS'},
            {
                'name': 'stage3',
                'status': 'IN_PROGRESS',
                'durationMillis': durationMillis,
            },
            {'name': 'stage4', 'status': 'NOT_EXECUTED'},
        ],
    }
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    Thread(target=set_finished).start()

    t0 = time.time()
    assert session.wait_job(g_url, 0.2)
    assert time.time() - t0 >= 0.5
    assert_progressbar_millis(capsys, 'stage3', durationMillis)


def test_retrieve_log(mock_url, session):
    content = 'some log content here'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    assert session.retrieve_log(g_url) == content


def test_dump_log(monkeypatch, session):
    content = 'some log content here'
    monkeypatch.setattr(session, 'retrieve_log', lambda a: content)
    filename = 'thing_other_master.txt'
    try:
        session.dump_log(g_url)
        assert os.path.isfile(filename)
        assert open(filename).read() == content
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_dump_binary_log(mock_url, session):
    content = b'binary log \xe2\x80 here'
    filename = 'thing_other_master.txt'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    try:
        session.dump_log(g_url)
        assert os.path.isfile(filename)
        assert open(filename).read() == 'binary log  here'
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_dump_log_stdout(mock_url, monkeypatch, capsys, session):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'dump', True)

    content = 'job output goes\n here'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    session.dump_log(g_url)
    out = capsys.readouterr()
    assert out.out == content
    assert not out.err


def test_get_stderr_size_os(terminal_size):
    """
    Test get stderr size when the os module has the get_terminal_size method.
    """
    size = get_stderr_size_unix()
    assert size.lines == 30
    assert size.columns == 30


def test_get_stderr_size_popen(monkeypatch):
    """
    Test get stderr size when the os module does not have the get_terminal_size
    method, and a popen must be used instead.
    """

    def fake_popen(*args, **kwargs):
        print('returning tihs')
        return StringIO('30 30')

    if hasattr(os, 'get_terminal_size'):
        monkeypatch.delattr(os, 'get_terminal_size')
    monkeypatch.setattr(os, 'popen', fake_popen)
    size = get_stderr_size_unix()
    assert size.lines == 30
    assert size.columns == 30


@pytest.mark.skipif('sys.platform == "win32"')
def test_get_stderr_size_stty(monkeypatch):
    """
    Test get stderr size when the os module does not have the get_terminal_size
    method, and a popen must be used instead.
    """
    if hasattr(os, 'get_terminal_size'):
        monkeypatch.delattr(os, 'get_terminal_size')
    try:
        size = get_stderr_size_unix()
    except OSError as error:
        pytest.skip(str(error))
    stty = os.popen('stty size -F /dev/stderr', 'r').read().split()
    assert size.lines == stty[0]
    assert size.columns == stty[1]


def test_show_progress(capsys, monkeypatch, terminal_size):
    """
    Set the necessary conditions and check that we can write a progress bar to
    stderr.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert is_progressbar_capable()
    assert_show_progressbar(capsys)


def test_show_progress_millis(capsys, tty):
    """
    Write a progressbar with time information and verify that the output looks
    OK.
    """
    assert_show_progressbar_millis(capsys)


def test_show_progress_no_tty(capsys, monkeypatch, terminal_size):
    """
    Check that we show a crippled progress bar when stderr is not a terminal.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: False)
    assert not is_progressbar_capable()
    assert_show_no_progressbar(capsys)


def test_show_progress_win32(capsys, monkeypatch, terminal_size):
    """
    Check that we show a crippled progress bar on Windows.
    """
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert not is_progressbar_capable()
    assert_show_no_progressbar(capsys)


def test_show_progress_no_get_size(capsys, monkeypatch):
    """
    Check that we show a crippled progress bar when we can't get the terminal
    size.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(launch_jenkins, 'get_stderr_size_unix', raise_error)
    assert not is_progressbar_capable()
    assert_show_no_progressbar(capsys)


def test_show_progress_force(capsys, monkeypatch, terminal_size):
    """
    Check that we can force the progress bar to be shown, even if the terminal
    is not technically capable.
    """
    # Force progress through config
    monkeypatch.setitem(launch_jenkins.CONFIG, 'progress', True)

    # Set all the right conditions
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)

    # Cripple conditions one by one
    with monkeypatch.context():
        monkeypatch.setattr(sys, 'platform', 'win32')
        assert is_progressbar_capable()
    with monkeypatch.context():
        monkeypatch.setattr(sys.stderr, 'isatty', lambda: False)
        assert is_progressbar_capable()
    with monkeypatch.context():
        # Even force is set, we can't progress bar without stderr size
        monkeypatch.setattr(
            launch_jenkins, 'get_stderr_size_unix', raise_error
        )
        assert not is_progressbar_capable()


def test_no_progress_quiet(capsys, monkeypatch, terminal_size):
    """
    Check that nothing is printed when the global "quiet" option is set.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert is_progressbar_capable()

    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', True)
    assert_show_empty_progress(capsys)


@pytest.mark.parametrize('func', [
    launch_build,
    wait_queue,
    wait_job,
    dump_log,
])
def test_func_nosession(func, monkeypatch):
    """
    Test the general backwards-compatible functions in the launch Jenkins
    module that do not require a session to be launched, and create their own
    silently.
    """
    def assert_session(session, url, *args, **kwargs):
        assert session.auth == g_auth
        assert url == g_url

    monkeypatch.setattr(Session, '_get_crumb', lambda self: None)
    monkeypatch.setattr(Session, func.__name__, assert_session)
    func(g_url, g_auth)
