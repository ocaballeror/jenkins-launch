import sys
import json
import time
from threading import Thread

import pytest


sys.path.append('..')
from launch_jenkins import is_parametrized
from launch_jenkins import launch_build
from launch_jenkins import wait_queue_item
from launch_jenkins import wait_for_job


url = "http://example.com:8080/job/thing/job/other/master"
g_auth = ('user', 'pwd')


@pytest.mark.parametrize('response,expect', [
    ({}, False),
    ({'key': 'value'}, False),
    ({'property': []}, False),
    ({'property': [{'key': 'value'}]}, False),
    ({'property': [{'parameterDefinitions': ['things']}]}, True),
])
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
        time.sleep(.5)
        resp = {'executable': {'url': 'some url'}}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    requests_mock.get(url + '/api/json', text='{}')
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_queue_item(url, g_auth, .2)
    assert time.time() - t0 >= .5


def test_wait_for_job(requests_mock):
    def set_finished():
        print('setting fisniehd')
        time.sleep(.5)
        print('setting fisniehd pt2')
        resp = {'result': 'success', 'displayName': 'name'}
        resp = json.dumps(resp)
        requests_mock.get(url + '/api/json', text=resp)

    resp = {'displayName': 'name'}
    requests_mock.get(url + '/api/json', text=json.dumps(resp))
    Thread(target=set_finished).start()

    t0 = time.time()
    wait_for_job(url, g_auth, .2)
    assert time.time() - t0 >= .5
