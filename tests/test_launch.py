import os
import sys
import json
import time
from threading import Thread

import pytest


sys.path.append('..')
import launch_jenkins
from launch_jenkins import is_parametrized
from launch_jenkins import launch_build
from launch_jenkins import wait_queue_item
from launch_jenkins import wait_for_job
from launch_jenkins import save_log_to_file
from launch_jenkins import show_progress


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
    config = launch_jenkins.CONFIG.copy()
    config['dump'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)

    content = 'job output goes\n here'
    requests_mock.get(url + '/consoleText', text=content)
    save_log_to_file(url, g_auth)
    out = capsys.readouterr()
    assert out.out == content
    assert not out.err


def test_show_progress(capsys, monkeypatch):
    class Dummy:
        def __init__(self, columns=0, rows=0):
            self.columns = columns
            self.rows = rows

    # Ensure we write the progress bar to stdout
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr(os, 'get_terminal_size', lambda x: Dummy(30, 30))

    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
    assert msg in outerr.err
    assert '.' * 10 in outerr.err
    assert not outerr.out

    config = launch_jenkins.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
    assert not outerr.err
    assert not outerr.out


def test_show_progress_no_tty(capsys, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'notwin32')
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
    assert outerr.err == '{}...\n'.format(msg)
    assert not outerr.out

    config = launch_jenkins.CONFIG.copy()
    config['quiet'] = True
    monkeypatch.setattr(launch_jenkins, 'CONFIG', config)
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
    assert not outerr.err
    assert not outerr.out


def test_show_progress_win32(capsys, monkeypatch):
    # Ensure we write the progress bar to stdout
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
    assert outerr.err == '{}...\n'.format(msg)
    assert not outerr.out
