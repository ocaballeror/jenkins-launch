import sys
import pytest

from launch_jenkins import launch_jenkins


call_log = []
job_url = 'http://instance:8080/job/thing/job/branch'
g_auth = ('username', 'pwd')
params = {}
queue_item = job_url + '/queue/item/1/'
build_url = job_url + '/1/'


@pytest.fixture
def parse_args(monkeypatch):
    def mock(*args, **kwargs):
        call_log.append(('parse_args', []))
        return build_url, g_auth, params

    monkeypatch.setattr(launch_jenkins, 'parse_args', mock)


@pytest.fixture
def launch_build(monkeypatch):
    def mock(*args, **kwargs):
        call_log.append(('launch_build', list(args)))
        return queue_item

    monkeypatch.setattr(launch_jenkins, 'launch_build', mock)


@pytest.fixture
def wait_queue_item(monkeypatch):
    def mock(location, auth):
        call_log.append(('wait_queue_item', [location, auth]))
        return build_url

    monkeypatch.setattr(launch_jenkins, 'wait_queue_item', mock)


@pytest.fixture
def wait_for_job(monkeypatch):
    def mock(build_url, auth):
        call_log.append(('wait_for_job', [build_url, auth]))
        return True

    monkeypatch.setattr(launch_jenkins, 'wait_for_job', mock)


@pytest.fixture
def wait_for_job_fail(monkeypatch):
    def mock(build_url, auth):
        call_log.append(('wait_for_job', [build_url, auth]))
        return False

    monkeypatch.setattr(launch_jenkins, 'wait_for_job', mock)


@pytest.fixture
def save_log_to_file(monkeypatch):
    def mock(build_url, auth):
        call_log.append(('save_log_to_file', [build_url, auth]))

    monkeypatch.setattr(launch_jenkins, 'save_log_to_file', mock)


@pytest.fixture
def launch_only(monkeypatch):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'mode', 'launch')


@pytest.fixture
def wait_only(monkeypatch):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'mode', 'wait')

@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', True)


@pytest.mark.usefixtures(
    'parse_args', 'launch_build', 'wait_queue_item', 'launch_only', 'quiet'
)
def test_launch_only(capsys):
    del call_log[:]

    launch_jenkins.main()
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, g_auth, params])
    assert call_log[2] == ('wait_queue_item', [queue_item, g_auth])

    # even if it was launched with -q, it should output the build url to stdout
    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out.strip() == build_url


@pytest.mark.usefixtures(
    'parse_args', 'wait_for_job', 'save_log_to_file', 'wait_only'
)
def test_wait_only():
    del call_log[:]

    assert launch_jenkins.main() == 0
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('wait_for_job', [build_url, g_auth])
    assert call_log[2] == ('save_log_to_file', [build_url, g_auth])


@pytest.mark.usefixtures('wait_for_job', 'save_log_to_file', 'wait_only')
def test_wait_main_invalid_build(monkeypatch):
    """
    Run the main function in wait_jenkins.py, but give it the url of a pipeline
    instead of a build (missing the build number at the end).

    The regex test should fail with a ValueError.
    """
    del call_log[:]

    new_argv = [__file__, '-j', job_url, '-u', g_auth[0], '-t', g_auth[1]]
    monkeypatch.setattr(sys, 'argv', new_argv)

    with pytest.raises(ValueError):
        launch_jenkins.main()
    assert not call_log


@pytest.mark.usefixtures(
    'parse_args', 'wait_for_job_fail', 'save_log_to_file', 'wait_only'
)
def test_wait_main_fail():
    assert launch_jenkins.main() == 1


@pytest.mark.usefixtures('wait_for_job', 'save_log_to_file', 'wait_only')
def test_wait_main_invalid_url(monkeypatch):
    del call_log[:]

    def parse_args_job_url(*args, **kwargs):
        "Return a job url (without a build number at the end)."
        return job_url, g_auth, params

    def parse_args_invalid(*args, **kwargs):
        "Return something that's not even a url."
        return 'asdfasdf', g_auth, params

    monkeypatch.setattr(launch_jenkins, 'parse_args', parse_args_invalid)
    with pytest.raises(ValueError):
        launch_jenkins.main()
    assert not call_log

    monkeypatch.setattr(launch_jenkins, 'parse_args', parse_args_job_url)
    with pytest.raises(ValueError):
        launch_jenkins.main()
    assert not call_log


@pytest.mark.usefixtures(
    'parse_args',
    'launch_build',
    'wait_queue_item',
    'wait_for_job',
    'save_log_to_file',
)
def test_launch_jenkins_main(monkeypatch):
    del call_log[:]

    assert launch_jenkins.main() == 0

    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, g_auth, params])
    assert call_log[2] == ('wait_queue_item', [queue_item, g_auth])
    assert call_log[3] == ('wait_for_job', [build_url, g_auth])
    assert call_log[4] == ('save_log_to_file', [build_url, g_auth])


@pytest.mark.usefixtures(
    'parse_args',
    'launch_build',
    'wait_queue_item',
    'wait_for_job_fail',
    'save_log_to_file',
)
def test_launch_jenkins_main_fail(monkeypatch):
    assert launch_jenkins.main() == 1
