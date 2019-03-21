import os
import sys
import json
import time
from threading import Thread
from collections import namedtuple

import pytest


import launch_and_wait
from launch_and_wait import is_parametrized
from launch_and_wait import launch_build
from launch_and_wait import wait_queue_item
from launch_and_wait import wait_for_job
from launch_and_wait import save_log_to_file

from .test_helper import assert_empty_progress
from .test_helper import assert_no_progressbar
from .test_helper import assert_progressbar


url = "http://example.com:8080/job/thing/job/other/job/master"
g_auth = ('user', 'pwd')


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

    # Set build properties as not parametrized
    requests_mock.get(url + '/api/json', text='{}')
    # Build with params
    assert launch_build(url, g_auth, {'a': 'b'}) == 'param queue'

    # Set build properties as parametrized
    props = {'property': [{'parameterDefinitions': ['thing']}]}
    props = json.dumps(props)
    requests_mock.get(url + '/api/json', text=props)

    # Launch parametrized build
    assert launch_build(url, g_auth) == 'param queue'
    assert launch_build(url, g_auth, {'a': 'b'}) == 'param queue'


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
        print('setting fisniehd')
        time.sleep(0.5)
        print('setting fisniehd pt2')
        resp = {'result': 'success', 'displayName': 'name'}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    resp = {'displayName': 'name'}
    requests_mock.get(url + '/api/json', text=json.dumps(resp))
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_for_job(url, g_auth, 0.2)
    assert time.time() - t0 >= 0.5


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


@pytest.mark.skipif('sys.version_info < (3, 0)')
def test_show_progress(capsys, monkeypatch):
    Size = namedtuple("terminal_size", "columns rows")

    # Ensure we write the progress bar to stdout
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(os, 'get_terminal_size', lambda x: Size(30, 30))
    assert_progressbar(capsys)

    config = launch_and_wait.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_and_wait, 'CONFIG', config)
    assert_empty_progress(capsys)


def test_show_progress_py2(capsys, monkeypatch):
    monkeypatch.setattr(sys, 'version_info', (2, 7, 9))
    assert_no_progressbar(capsys)


def test_show_progress_no_tty(capsys, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)

    config = launch_and_wait.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_and_wait, 'CONFIG', config)
    assert_empty_progress(capsys)


def test_show_progress_win32(capsys, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    assert_no_progressbar(capsys)
