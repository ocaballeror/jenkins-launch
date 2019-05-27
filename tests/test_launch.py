from __future__ import unicode_literals

import os
import sys
import json
import time
from io import StringIO
from threading import Thread

import pytest


import launch_jenkins.launch_and_wait as launch_jenkins
from launch_jenkins import is_parametrized
from launch_jenkins import launch_build
from launch_jenkins import wait_queue_item
from launch_jenkins import wait_for_job
from launch_jenkins import save_log_to_file
from launch_jenkins import parse_args
from launch_jenkins import parse_job_url
from launch_jenkins import get_stderr_size_unix
from launch_jenkins import is_progressbar_capable
from launch_jenkins import HTTPError

from .test_helper import assert_empty_progress
from .test_helper import assert_no_progressbar
from .test_helper import assert_progressbar
from .test_helper import terminal_size  # noqa: F401
from .test_helper import raise_error


url = "http://example.com:8080/job/thing/job/other/job/master"
g_auth = ('user', 'pwd')
g_params = ['-j', url, '-u', g_auth[0], '-t', g_auth[1]]


class FakeResponse:
    def __init__(self, text='', headers=None, status_code=200):
        self.text = text
        self.headers = headers or {}
        self.status_code = status_code

    def __iter__(self):
        text = self.text
        encoded = text.encode('utf-8')
        self.text = encoded
        try:
            yield self
        finally:
            self.text = text


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


def test_basic_argv(monkeypatch):
    new_argv = ['python'] + g_params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (url, g_auth, {})


def test_argv_params(monkeypatch):
    params = ['key=value', 'keyt=other value', 'empty=', 'truth=1 == 0']
    build_params = {
        'key': 'value',
        'keyt': 'other value',
        'empty': '',
        'truth': '1 == 0',
    }
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (url, g_auth, build_params)


@pytest.mark.parametrize(
    'params', [(['key']), (['key: value']), (['key=value', 'value: key'])]
)
def test_argv_params_wrong_format(monkeypatch, params, capsys):
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit):
        parse_args()
    out, err = capsys.readouterr()
    assert 'use key=value format' in err


def test_optional_flags(monkeypatch):
    """
    Check that the known optional flags are accepted.
    """
    params = ['-q', '--dump', '--progress']
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    config = launch_jenkins.CONFIG.copy()
    try:
        parse_args()
        assert launch_jenkins.CONFIG['dump']
        assert launch_jenkins.CONFIG['quiet']
        assert launch_jenkins.CONFIG['progress']
    finally:
        launch_jenkins.CONFIG = config


@pytest.mark.parametrize(
    'response,expect',
    [
        ({}, False),
        ({'key': 'value'}, False),
        ({'property': []}, False),
        ({'property': [{'key': 'value'}]}, False),
        ({'property': [{'parameterDefinitions': ['things']}]}, True),
    ],
)
def test_is_parametrized(mock_url, response, expect):
    mock_url({'url': url + '/api/json', 'text': json.dumps(response)})
    assert is_parametrized(url, g_auth) == expect


def test_parse_job_url():
    assert parse_job_url(url) == (url, [])
    assert parse_job_url(url + '/') == (url, [])
    assert parse_job_url(url + '/build') == (url, [])
    assert parse_job_url(url + '/build/') == (url, [])
    assert parse_job_url(url + '/buildWithParameters') == (url, [])
    assert parse_job_url(url + '/buildWithParameters/') == (url, [])


def test_parse_job_url_params():
    build_url = url + '/buildWithParameters?a=b'
    assert parse_job_url(build_url) == (url, ['a=b'])

    build_url = url + '/buildWithParameters?a=b&c=d'
    assert parse_job_url(build_url) == (url, ['a=b', 'c=d'])


@pytest.mark.parametrize(
    'job_url',
    [
        'http',
        url + '/asdf',
        url + '/build?a=b',
        url + '/buildwiththings?a=b',
        url + '/buildwithparameters',
        url + '/buildwithparameters?a=b',
    ],
    ids=[
        'not a url',
        'does last section is not a job',
        '/build takes no params',
        'invalid api name',
        'lowercase buildwithparameters',
        'lowercase buildwithparameters with params',
    ],
)
def test_parse_job_url_error(job_url):
    with pytest.raises(ValueError) as error:
        parse_job_url(job_url)
    assert 'invalid job url' in str(error.value).lower()


def test_build_no_params(mock_url):
    headers = {'Location': 'some queue'}
    mock_url(
        [
            # Return build location
            dict(url=url + '/build', headers=headers),
            # Set build properties as not parametrized
            dict(url=url + '/api/json', text='{}'),
        ]
    )

    # Launch build
    assert launch_build(url, g_auth, {}) == 'some queue'


def test_build_with_params(mock_url):
    headers = {'Location': 'param queue'}

    # Set build properties as parametrized
    props = {'property': [{'parameterDefinitions': ['thing']}]}
    props = json.dumps(props)

    mock_url(
        [
            dict(url=url + '/buildWithParameters', headers=headers),
            dict(url=url + '/api/json', text=props),
        ]
    )

    # Launch parametrized build
    assert launch_build(url, g_auth) == 'param queue'
    assert launch_build(url, g_auth, {'a': 'b'}) == 'param queue'


def test_build_unparametrized_with_params(monkeypatch):
    """
    Check that an error is raised when the user passes parameters to a
    non-parametrized job.
    """
    monkeypatch.setattr(launch_jenkins, 'is_parametrized', lambda x, y: False)
    with pytest.raises(RuntimeError) as error:
        launch_build(url, g_auth, params={'key': 'value'})
        assert 'parameters' in str(error)


def test_launch_error(mock_url):
    mock_url(
        [
            dict(url=url + '/api/json', text='{}'),
            dict(url=url + '/build', status_code=400),
        ]
    )

    with pytest.raises(HTTPError):
        launch_build(url, g_auth)


def test_launch_error_no_queue(mock_url):
    headers = {'Header': 'value'}
    mock_url(
        [
            dict(url=url + '/build', headers=headers),
            dict(url=url + '/api/json', text='{}'),
        ]
    )

    # Response has no location header
    with pytest.raises(AssertionError):
        launch_build(url, g_auth, {})

    headers = {'Location': 'this is not the word you are looking for'}
    mock_url(dict(url=url + '/build', headers=headers))
    # Location has no queue url
    with pytest.raises(AssertionError):
        launch_build(url, g_auth, {})


def test_wait_queue_item(mock_url):
    def set_finished():
        time.sleep(0.5)
        resp = {'executable': {'url': 'some url'}}
        resp = json.dumps(resp)
        mock_url(dict(url=url + '/api/json', text=resp))

    mock_url(dict(url=url + '/api/json', text='{}'))
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_queue_item(url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_for_job(mock_url):
    def set_finished():
        time.sleep(0.5)
        resp = {'result': 'success', 'displayName': 'name'}
        resp = json.dumps(resp)
        mock_url(dict(url=url + '/api/json', text=resp))

    resp = {'displayName': 'name'}
    mock_url(dict(url=url + '/api/json', text=json.dumps(resp)))
    Thread(target=set_finished).start()

    t0 = time.time()
    assert wait_for_job(url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_for_job_fail(mock_url):
    """
    Check that wait_for_job returns False on any build result other than
    "success".
    """

    def set_finished():
        time.sleep(0.5)
        resp = {'result': 'failure', 'displayName': 'name'}
        resp = json.dumps(resp)
        mock_url(dict(url=url + '/api/json', text=resp))

    resp = {'displayName': 'name'}
    mock_url(dict(url=url + '/api/json', text=json.dumps(resp)))
    Thread(target=set_finished).start()

    assert not wait_for_job(url, g_auth, 0.2)


def test_save_log_to_file(mock_url):
    content = 'some log content here'
    filename = 'thing_other_master.txt'
    mock_url(dict(url=url + '/consoleText', text=content))
    try:
        save_log_to_file(url, g_auth)
        assert os.path.isfile(filename)
        assert open(filename).read() == content
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_dump_log_stdout(mock_url, monkeypatch, capsys):
    config = launch_jenkins.CONFIG.copy()
    config['dump'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)

    content = 'job output goes\n here'
    mock_url(dict(url=url + '/consoleText', text=content))
    save_log_to_file(url, g_auth)
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
    assert_progressbar(capsys)


def test_show_progress_no_tty(capsys, monkeypatch, terminal_size):
    """
    Check that we show a crippled progress bar when stderr is not a terminal.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: False)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_win32(capsys, monkeypatch, terminal_size):
    """
    Check that we show a crippled progress bar on Windows.
    """
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_no_get_size(capsys, monkeypatch):
    """
    Check that we show a crippled progress bar when we can't get the terminal
    size.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(launch_jenkins, 'get_stderr_size_unix', raise_error)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_force(capsys, monkeypatch, terminal_size):
    """
    Check that we can force the progress bar to be shown, even if the terminal
    is not technically capable.
    """
    # Force progress through config
    config = launch_jenkins.CONFIG.copy()
    config['progress'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)

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

    config = launch_jenkins.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)
    assert_empty_progress(capsys)
