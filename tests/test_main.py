import pytest

import launch_jenkins
import wait_jenkins
import launch_and_wait


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


def test_wait_main_invalid_url(monkeypatch):
    call_log.clear()

    def parse_args_job_url():
        "Return a job url (without a build number at the end)."
        return job_url, g_auth, params

    def parse_args_invalid():
        "Return something that's not even a url."
        return 'asdfasdf', g_auth, params

    monkeypatch.setattr(wait_jenkins, 'wait_for_job', wait_for_job)
    monkeypatch.setattr(wait_jenkins, 'save_log_to_file', save_log_to_file)

    monkeypatch.setattr(wait_jenkins, 'parse_args', parse_args_invalid)
    with pytest.raises(ValueError):
        wait_jenkins.main()
    assert not call_log

    monkeypatch.setattr(wait_jenkins, 'parse_args', parse_args_job_url)
    with pytest.raises(ValueError):
        wait_jenkins.main()
    assert not call_log


def test_launch_and_wait_main(monkeypatch):
    call_log.clear()

    monkeypatch.setattr(launch_and_wait, 'parse_args', parse_args)
    monkeypatch.setattr(launch_and_wait, 'launch_build', launch_build)
    monkeypatch.setattr(launch_and_wait, 'wait_queue_item', wait_queue_item)
    monkeypatch.setattr(launch_and_wait, 'wait_for_job', wait_for_job)
    monkeypatch.setattr(launch_and_wait, 'save_log_to_file', save_log_to_file)

    launch_and_wait.main()

    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, g_auth, params])
    assert call_log[2] == ('wait_queue_item', [queue_item, g_auth])
    assert call_log[3] == ('wait_for_job', [True])
    assert call_log[4] == ('save_log_to_file', [])
