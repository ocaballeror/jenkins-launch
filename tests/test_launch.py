from __future__ import unicode_literals

import os
import sys
import json
import time
from io import StringIO
from threading import Thread

import pytest

if sys.version_info >= (3,):
    from urllib.parse import parse_qs
else:
    from urlparse import parse_qs

    range = xrange  # noqa:F821


from launch_jenkins import launch_jenkins
from launch_jenkins import get_url
from launch_jenkins import get_job_params
from launch_jenkins import launch_build
from launch_jenkins import get_job_status
from launch_jenkins import wait_queue_item
from launch_jenkins import wait_for_job
from launch_jenkins import retrieve_log
from launch_jenkins import save_log_to_file
from launch_jenkins import parse_args
from launch_jenkins import parse_job_url
from launch_jenkins import get_stderr_size_unix
from launch_jenkins import is_progressbar_capable
from launch_jenkins import HTTPError

from .conftest import FakeResponse
from .test_helper import assert_show_empty_progress
from .test_helper import assert_show_no_progressbar
from .test_helper import assert_show_progressbar
from .test_helper import assert_show_progressbar_millis
from .test_helper import assert_progressbar_millis
from .test_helper import raise_error


g_url = "http://example.com:8080/job/thing/job/other/job/master"
g_auth = ('user', 'pwd')
g_auth_b64 = 'Basic dXNlcjpwd2Q='
g_params = ['-j', g_url, '-u', g_auth[0], '-t', g_auth[1]]


@pytest.mark.parametrize(
    'args',
    [
        [],
        ['-j', 'asdf', '-u', 'asdf'],
        ['-j', 'asdf', '-u', 'asdf', '-t'],
        ['-j', 'asdf', '-t', 'asdf'],
        ['-j', 'asdf', '-u', '-t', 'asdf'],
        ['-u', 'asdf', '-t', 'asdf'],
        ['-j', '-u', 'asdf', '-t', 'asdf'],
    ],
    ids=[
        'Empty args',
        '-t required',
        '-t needs an argument',
        '-u required',
        '-u needs an argument',
        '-j required',
        '-j needs an argument',
    ],
)
def test_parse_incomplete_args(monkeypatch, args):
    new_argv = ['python'] + args
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit):
        parse_args()


@pytest.mark.parametrize(
    'args',
    [['--launch-only', '--wait-only']],
    ids=['Launch only and wait only'],
)
def test_parse_incompatible_args(monkeypatch, args):
    new_argv = ['python'] + g_params + args
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit) as error:
        parse_args()
        assert 'not allowed with argument' in str(error.value)


def test_basic_argv(monkeypatch):
    new_argv = ['python'] + g_params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (g_url, g_auth, {})


def test_argv_params(monkeypatch):
    params = [
        'key=value',
        'keyt=other value',
        'empty=',
        'truth=1 == 0',
        's p a c e s = are cool',
    ]
    build_params = {
        'key': 'value',
        'keyt': 'other value',
        'empty': '',
        'truth': '1 == 0',
        's p a c e s': 'are cool',
    }
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (g_url, g_auth, build_params)


@pytest.mark.parametrize(
    'params', [['key'], ['key: value'], ['key=value', 'value: key']]
)
def test_argv_params_wrong_format(monkeypatch, params):
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(ValueError) as error:
        parse_args()
        assert 'use key=value format' in error.value


def test_optional_flags(monkeypatch, config):
    """
    Check that the known optional flags are accepted.
    """
    params = ['-q', '--dump', '--progress']
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    parse_args()
    assert launch_jenkins.CONFIG['dump']
    assert launch_jenkins.CONFIG['quiet']
    assert launch_jenkins.CONFIG['progress']


@pytest.mark.parametrize(
    'arg, url, mode',
    [
        ('', g_url, 'full'),
        ('-l', g_url, 'launch'),
        ('-w', g_url + '/42', 'wait'),
    ],
    ids=['full', 'launch only', 'wait only'],
)
def test_launch_wait_only(arg, url, mode, monkeypatch, config):
    new_argv = ['python', '-j', url, '-u', g_auth[0], '-t', g_auth[1]]
    if arg:
        new_argv += [arg]
    monkeypatch.setattr(sys, 'argv', new_argv)
    parse_args()
    assert launch_jenkins.CONFIG['mode'] == mode


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
def test_get_job_params_empty(mock_url, response):
    """
    Get job params when there is no parameter definition
    """
    mock_url({'url': g_url + '/api/json', 'text': json.dumps(response)})
    assert get_job_params(g_url, g_auth) == {}


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
def test_get_job_params(mock_url, response, expect):
    response = {
        'property': [
            {
                '_class': 'hudson.model.ParametersDefinitionProperty',
                'parameterDefinitions': response,
            }
        ]
    }
    mock_url({'url': g_url + '/api/json', 'text': json.dumps(response)})
    assert get_job_params(g_url, g_auth) == expect


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


def test_get_url(monkeypatch):
    requests = []
    text = 'hello world'
    resp_headers = dict(location='here')
    url = 'http://example.com'

    def fake_response(r):
        requests.append(r)
        return FakeResponse(text, headers=resp_headers)

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    resp = get_url(url, auth=g_auth)
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


def test_get_url_escaped(mock_url):
    text = 'yes'
    url = 'http://example.com/feature%252Fhelloworld'
    mock_url(dict(url=url, text=text))

    assert get_url(url, auth=g_auth).text == text


def test_get_url_data(monkeypatch):
    requests = []
    url = 'http://example.com'
    data = {'simple': 'hello', 'space': 'hello world', 'weird': 'jk34$"/ &aks'}

    def fake_response(r):
        requests.append(r)
        return FakeResponse()

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    get_url(url, auth=g_auth, data=data)

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


def test_get_url_stream(monkeypatch):
    requests = []
    text = 'a' * 8192 + 'b' * 100
    url = 'http://example.com'

    def fake_response(r):
        requests.append(r)
        return FakeResponse(text)

    monkeypatch.setattr(launch_jenkins, 'urlopen', fake_response)
    resp = get_url(url, auth=g_auth, stream=True)
    assert not hasattr(resp, 'text')
    assert next(resp).text.decode('utf-8') == 'a' * 8192
    assert next(resp).text.decode('utf-8') == 'b' * 100
    with pytest.raises(StopIteration):
        next(resp)


def test_build_no_params(mock_url, unparametrized):
    headers = {'Location': 'some queue'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))

    # Launch build
    assert launch_build(g_url, g_auth, {}) == 'some queue'


def test_build_with_params(mock_url, monkeypatch):
    headers = {'Location': 'param queue'}

    # Set build properties as parametrized
    def mock_get_job_params(*args):
        return {'param': None}

    monkeypatch.setattr(launch_jenkins, 'get_job_params', mock_get_job_params)

    mock_url(
        dict(
            url=g_url + '/buildWithParameters', headers=headers, method='POST'
        )
    )

    # Launch parametrized build
    assert launch_build(g_url, g_auth) == 'param queue'
    assert launch_build(g_url, g_auth, {'param': 'asdf'}) == 'param queue'


def test_launch_error(mock_url, unparametrized):
    mock_url(dict(url=g_url + '/build', status_code=400, method='POST'))

    with pytest.raises(HTTPError):
        launch_build(g_url, g_auth)


def test_launch_error_no_queue(mock_url, unparametrized):
    headers = {'Header': 'value'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))

    # Response has no location header
    with pytest.raises(AssertionError):
        launch_build(g_url, g_auth, {})

    headers = {'Location': 'this is not the word you are looking for'}
    mock_url(dict(url=g_url + '/build', headers=headers, method='POST'))
    # Location has no queue url
    with pytest.raises(AssertionError):
        launch_build(g_url, g_auth, {})


def test_wait_queue_item(mock_url):
    def set_finished():
        time.sleep(0.5)
        resp = {'executable': {'url': 'some url'}}
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/api/json', text=resp))

    mock_url(dict(url=g_url + '/api/json', text='{}'))
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_queue_item(g_url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_queue_item_cancelled(mock_url):
    def set_finished():
        time.sleep(0.5)
        resp = {'cancelled': True}
        resp = json.dumps(resp)
        mock_url(dict(url=g_url + '/api/json', text=resp))

    mock_url(dict(url=g_url + '/api/json', text='{}'))
    Thread(target=set_finished).start()

    t0 = time.time()
    with pytest.raises(RuntimeError):
        wait_queue_item(g_url, g_auth, 0.2)
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
def test_get_job_status(mock_url, status, expect):
    stage = {'name': 'stage', 'status': status}
    resp = {'name': 'name', 'status': status, 'stages': [stage]}
    mock_url(dict(url=g_url + '/wfapi/describe', text=json.dumps(resp)))
    assert get_job_status(g_url, g_auth) == (expect, stage)


def test_get_job_status_in_progress(mock_url):
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
    assert get_job_status(g_url, g_auth) == (None, current)


def test_get_job_status_false_negative(mock_url):
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
    assert get_job_status(g_url, g_auth) == (True, last)


@pytest.mark.parametrize(
    'status, success',
    [('SUCCESS', True), ('FAILED', False), ('CANCELLED', False)],
)
def test_wait_for_job(mock_url, status, success):
    """
    Check that wait_for_job returns True or False when a build reaches a final
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
    assert wait_for_job(g_url, g_auth, 0.2) == success
    assert time.time() - t0 >= 0.5


def test_wait_for_job_nonexistent(monkeypatch):
    status_code = 400
    build_number = 65
    build_url = 'http://example.com/%s' % build_number

    def raise_httperror(*args, **kwargs):
        raise HTTPError(build_url, status_code, 'Mock http error', {}, None)

    monkeypatch.setattr(launch_jenkins, 'get_url', raise_httperror)
    with pytest.raises(HTTPError) as error:
        wait_for_job(build_url, None)
        assert str(error.value) == 'Mock http error'

    status_code = 404
    with pytest.raises(HTTPError) as error:
        wait_for_job(build_url, None)
        assert str(error.value) == 'Build #%s does not exist' % build_number


def test_wait_for_job_get_duration(mock_url, capsys, tty):
    """
    Return the list of stages and assert that wait_for_job can find the current
    one and extract its duration.
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
    assert wait_for_job(g_url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5
    assert_progressbar_millis(capsys, 'stage3', durationMillis)


def test_retrieve_log(mock_url):
    content = 'some log content here'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    assert retrieve_log(g_url, g_auth) == content


def test_save_log_to_file(monkeypatch):
    content = 'some log content here'
    monkeypatch.setattr(launch_jenkins, 'retrieve_log', lambda a, b: content)
    filename = 'thing_other_master.txt'
    try:
        save_log_to_file(g_url, g_auth)
        assert os.path.isfile(filename)
        assert open(filename).read() == content
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_save_binary_log_to_file(mock_url):
    content = b'binary log \xe2\x80 here'
    filename = 'thing_other_master.txt'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    try:
        save_log_to_file(g_url, g_auth)
        assert os.path.isfile(filename)
        assert open(filename).read() == 'binary log  here'
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_dump_log_stdout(mock_url, monkeypatch, capsys):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'dump', True)

    content = 'job output goes\n here'
    mock_url(dict(url=g_url + '/consoleText', text=content))
    save_log_to_file(g_url, g_auth)
    out = capsys.readouterr()
    assert out.out == content
    assert not out.err


def test_get_stderr_size_os(terminal_size):
    """
    Test get stderr size when the os module has the get_terminal_size method.
    """
    size = get_stderr_size_unix()
    assert size.rows == 30
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
    assert size.rows == 30
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
    assert size.rows == stty[0]
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
