import pytest

import launch_jenkins
import wait_jenkins


call_log = []
job_url = 'http://instance:8080/job/thing/job/branch'
g_auth = ('username', 'pwd')
params = {}
queue_item = job_url + '/queue/item/1'
build_url = job_url + '/1'

def parse_args():
    call_log.append(('parse_args', []))
    return build_url, g_auth, params

def launch_build(*args):
    call_log.append(('launch_build', list(args)))
    return queue_item

def wait_queue_item(location, auth):
    call_log.append(('wait_queue_item', [location, auth]))
    return build_url

def wait_for_job(build_url, auth):
    call_log.append(('wait_for_job', [build_url, auth]))
    return True

def save_log_to_file(build_url, auth):
    call_log.append(('save_log_to_file', [build_url, auth]))


def test_launch_main(monkeypatch):
    call_log.clear()

    monkeypatch.setattr(launch_jenkins, 'parse_args', parse_args)
    monkeypatch.setattr(launch_jenkins, 'launch_build', launch_build)
    monkeypatch.setattr(launch_jenkins, 'wait_queue_item', wait_queue_item)

    launch_jenkins.main()
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, g_auth, params])
    assert call_log[2] == ('wait_queue_item', [queue_item, g_auth])


def test_wait_main(monkeypatch):
    call_log.clear()

    monkeypatch.setattr(wait_jenkins, 'parse_args', parse_args)
    monkeypatch.setattr(wait_jenkins, 'wait_for_job', wait_for_job)
    monkeypatch.setattr(wait_jenkins, 'save_log_to_file', save_log_to_file)

    wait_jenkins.main()
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('wait_for_job', [True])
    assert call_log[2] == ('save_log_to_file', [])


def test_wait_main_invalid_build(monkeypatch):
    call_log.clear()

    def parse_args_invalid():
        return job_url, g_auth, params

    monkeypatch.setattr(wait_jenkins, 'parse_args', parse_args_invalid)
    monkeypatch.setattr(wait_jenkins, 'wait_for_job', wait_for_job)
    monkeypatch.setattr(wait_jenkins, 'save_log_to_file', save_log_to_file)

    with pytest.raises(ValueError):
        wait_jenkins.main()

    assert not call_log