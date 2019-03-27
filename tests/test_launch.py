import os
import sys
import json
import time
from io import StringIO
from threading import Thread

import pytest


import launch_and_wait
from launch_and_wait import is_parametrized
from launch_and_wait import launch_build
from launch_and_wait import wait_queue_item
from launch_and_wait import wait_for_job
from launch_and_wait import save_log_to_file
from launch_and_wait import parse_args
from launch_and_wait import parse_job_url
from launch_and_wait import get_stderr_size_unix
from launch_and_wait import is_progressbar_capable

from .test_helper import assert_empty_progress
from .test_helper import assert_no_progressbar
from .test_helper import assert_progressbar
from .test_helper import set_get_terminal_size
from .test_helper import raise_error


url = "http://example.com:8080/job/thing/job/other/job/master"
g_auth = ('user', 'pwd')
g_params = ['-j', url, '-u', g_auth[0], '-t', g_auth[1]]


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
    params = ['key=value', 'keyt=other value']
    build_params = {'key': 'value', 'keyt': 'other value'}
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (url, g_auth, build_params)


def test_optional_flags(monkeypatch):
    """
    Check that the known optional flags are accepted.
    """
    params = ['-q', '--dump', '--progress']
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    config = launch_and_wait.CONFIG.copy()
    try:
        parse_args()
        assert launch_and_wait.CONFIG['dump']
        assert launch_and_wait.CONFIG['quiet']
        assert launch_and_wait.CONFIG['progress']
    finally:
        launch_and_wait.CONFIG = config


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
def test_is_parametrized(requests_mock, response, expect):
    response = json.dumps(response)
    requests_mock.get(url + '/api/json', text=response)
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
        'http://thing:8080/job/name/anotherslashjobhere',
        url + '/asdf',
        url + '/build?a=b',
        url + '/buildwiththings?a=b',
        url + '/buildwithparameters',
        url + '/buildwithparameters?a=b',
    ],
)
def test_parse_job_url_error(job_url):
    with pytest.raises(ValueError) as error:
        parse_job_url(job_url)
    assert 'invalid job url' in str(error.value).lower()


def test_build_no_params(requests_mock):
    headers = {'Location': 'some queue'}
    requests_mock.post(url + '/build', headers=headers)

    # Set build properties as not parametrized
    requests_mock.get(url + '/api/json', text='{}')
    # Launch build
    assert launch_build(url, g_auth, {}) == 'some queue'


def test_build_with_params(requests_mock):
    headers = {'Location': 'param queue'}
    requests_mock.post(url + '/buildWithParameters', headers=headers)

    # Set build properties as parametrized
    props = {'property': [{'parameterDefinitions': ['thing']}]}
    props = json.dumps(props)
    requests_mock.get(url + '/api/json', text=props)

    # Launch parametrized build
    assert launch_build(url, g_auth) == 'param queue'
    assert launch_build(url, g_auth, {'a': 'b'}) == 'param queue'


def test_build_unparametrized_with_params(monkeypatch):
    """
    Check that an error is raised when the user passes parameters to a
    non-parametrized job.
    """
    monkeypatch.setattr(launch_and_wait, 'is_parametrized', lambda x, y: False)
    with pytest.raises(RuntimeError) as error:
        launch_build(url, g_auth, params={'key': 'value'})
        assert 'parameters' in str(error)


def test_launch_error(requests_mock):
    requests_mock.get(url + '/api/json', text='{}')
    requests_mock.post(url + '/build', status_code=400)

    with pytest.raises(RuntimeError):
        launch_build(url, g_auth)


def test_launch_error_no_queue(requests_mock):
    headers = {'Header': 'value'}
    requests_mock.post(url + '/build', headers=headers)
    requests_mock.get(url + '/api/json', text='{}')

    # Response has no location header
    with pytest.raises(AssertionError):
        launch_build(url, g_auth, {})

    headers = {'Location': 'this is not the word you are looking for'}
    requests_mock.post(url + '/build', headers=headers)
    # Location has no queue url
    with pytest.raises(AssertionError):
        launch_build(url, g_auth, {})


def test_wait_queue_item(requests_mock):
    def set_finished():
        time.sleep(0.5)
        resp = {'executable': {'url': 'some url'}}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    requests_mock.get(url + '/api/json', text='{}')
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_queue_item(url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_for_job(requests_mock):
    def set_finished():
        time.sleep(0.5)
        resp = {'result': 'success', 'displayName': 'name'}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    resp = {'displayName': 'name'}
    requests_mock.get(url + '/api/json', text=json.dumps(resp))
    Thread(target=set_finished).start()

    t0 = time.time()
    assert wait_for_job(url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


def test_wait_for_job_fail(requests_mock):
    """
    Check that wait_for_job returns False on any build result other than
    "success".
    """

    def set_finished():
        time.sleep(0.5)
        resp = {'result': 'failure', 'displayName': 'name'}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    resp = {'displayName': 'name'}
    requests_mock.get(url + '/api/json', text=json.dumps(resp))
    Thread(target=set_finished).start()

    assert not wait_for_job(url, g_auth, 0.2)


def test_save_log_to_file(requests_mock):
    content = 'some log content here'
    filename = 'thing_other_master.txt'
    requests_mock.get(url + '/consoleText', text=content)
    try:
        save_log_to_file(url, g_auth)
        assert os.path.isfile(filename)
        assert open(filename).read() == content
    finally:
        if os.path.isfile(filename):
            os.remove(filename)


def test_dump_log_stdout(requests_mock, monkeypatch, capsys):
    config = launch_and_wait.CONFIG.copy()
    config['dump'] = True
    monkeypatch.setattr(launch_and_wait, 'CONFIG', config)

    content = 'job output goes\n here'
    requests_mock.get(url + '/consoleText', text=content)
    save_log_to_file(url, g_auth)
    out = capsys.readouterr()
    assert out.out == content
    assert not out.err


def test_get_stderr_size_os(monkeypatch):
    """
    Test get stderr size when the os module has the get_terminal_size method.
    """
    set_get_terminal_size(monkeypatch)
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


def test_show_progress(capsys, monkeypatch):
    """
    Set the necessary conditions and check that we can write a progress bar to
    stderr.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    set_get_terminal_size(monkeypatch)
    assert is_progressbar_capable()
    assert_progressbar(capsys)


def test_show_progress_no_tty(capsys, monkeypatch):
    """
    Check that we show a crippled progress bar when stderr is not a terminal.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: False)
    set_get_terminal_size(monkeypatch)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_win32(capsys, monkeypatch):
    """
    Check that we show a crippled progress bar on Windows.
    """
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    set_get_terminal_size(monkeypatch)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_no_get_size(capsys, monkeypatch):
    """
    Check that we show a crippled progress bar when we can't get the terminal
    size.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(launch_and_wait, 'get_stderr_size_unix', raise_error)
    assert not is_progressbar_capable()
    assert_no_progressbar(capsys)


def test_show_progress_force(capsys, monkeypatch):
    """
    Check that we can force the progress bar to be shown, even if the terminal
    is not technically capable.
    """
    # Force progress through config
    config = launch_and_wait.CONFIG.copy()
    config['progress'] = True
    monkeypatch.setattr(launch_and_wait, 'CONFIG', config)

    # Set all the right conditions
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    set_get_terminal_size(monkeypatch)

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
            launch_and_wait, 'get_stderr_size_unix', raise_error
        )
        assert not is_progressbar_capable()


def test_no_progress_quiet(capsys, monkeypatch):
    """
    Check that nothing is printed when the global "quiet" option is set.
    """
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    set_get_terminal_size(monkeypatch)
    assert is_progressbar_capable()

    config = launch_and_wait.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_and_wait, 'CONFIG', config)
    assert_empty_progress(capsys)
