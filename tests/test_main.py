import sys
import pytest

from launch_jenkins import launch_jenkins
from launch_jenkins import __version__


call_log = []
job_url = 'http://example.com/job/thing/job/branch'
g_auth = ('username', 'pwd')
params = {}
queue_item = job_url + '/queue/item/1/'
build_url = job_url + '/1/'


@pytest.fixture
def session(monkeypatch):
    session = launch_jenkins.Session(job_url, g_auth)
    monkeypatch.setattr(launch_jenkins, 'Session', lambda a, b: session)
    return session


@pytest.fixture
def parse_args(monkeypatch):
    def mock(*args, **kwargs):
        call_log.append(('parse_args', []))
        return build_url, g_auth, params

    monkeypatch.setattr(launch_jenkins, 'parse_args', mock)


@pytest.fixture
def launch_build(monkeypatch, session):
    def mock(url, params):
        call_log.append(('launch_build', [url, params]))
        return queue_item

    monkeypatch.setattr(session, 'launch_build', mock)


@pytest.fixture
def wait_queue(monkeypatch, session):
    def mock(location):
        call_log.append(('wait_queue', [location]))
        return build_url

    monkeypatch.setattr(session, 'wait_queue', mock)


@pytest.fixture
def wait_job(monkeypatch, session):
    def mock(build_url):
        call_log.append(('wait_job', [build_url]))
        return True

    monkeypatch.setattr(session, 'wait_job', mock)


@pytest.fixture
def wait_job_fail(monkeypatch, session):
    def mock(build_url):
        call_log.append(('wait_job', [build_url]))
        return False

    monkeypatch.setattr(session, 'wait_job', mock)


@pytest.fixture
def dump_log(monkeypatch, session):
    def mock(build_url):
        call_log.append(('dump_log', [build_url]))

    monkeypatch.setattr(session, 'dump_log', mock)


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
    'parse_args', 'launch_build', 'wait_queue', 'launch_only', 'quiet',
)
def test_launch_only(capsys):
    del call_log[:]

    launch_jenkins.main()
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, params])
    assert call_log[2] == ('wait_queue', [queue_item])

    # even if it was launched with -q, it should output the build url to stdout
    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out.strip() == build_url


@pytest.mark.usefixtures(
    'parse_args', 'wait_job', 'dump_log', 'wait_only'
)
def test_wait_only():
    del call_log[:]

    assert launch_jenkins.main() == 0
    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('wait_job', [build_url])
    assert call_log[2] == ('dump_log', [build_url])


@pytest.mark.usefixtures(
    'parse_args', 'wait_job_fail', 'dump_log', 'wait_only'
)
def test_wait_main_fail():
    assert launch_jenkins.main() == 1


@pytest.mark.usefixtures('wait_job', 'dump_log')
def test_wait_main_invalid_url(monkeypatch):
    """
    Check that main() raises an error when specifying wait-only and passing a
    url without a build number at the end.
    """
    del call_log[:]

    basic_argv = [__file__, '-u', g_auth[0], '-t', g_auth[1], '-w']
    new_argv = list(basic_argv)  # not using list.copy because python2
    new_argv += ['-j', job_url]
    monkeypatch.setattr(sys, 'argv', new_argv)

    with pytest.raises(ValueError):
        launch_jenkins.main()
    assert not call_log


@pytest.mark.usefixtures(
    'parse_args',
    'launch_build',
    'wait_queue',
    'wait_job',
    'dump_log',
)
def test_launch_jenkins_main(monkeypatch):
    del call_log[:]

    monkeypatch.setitem(launch_jenkins.CONFIG, 'mode', 'full')
    assert launch_jenkins.main() == 0

    assert call_log[0] == ('parse_args', [])
    assert call_log[1] == ('launch_build', [build_url, params])
    assert call_log[2] == ('wait_queue', [queue_item])
    assert call_log[3] == ('wait_job', [build_url])
    assert call_log[4] == ('dump_log', [build_url])


@pytest.mark.usefixtures(
    'parse_args',
    'launch_build',
    'wait_queue',
    'wait_job_fail',
    'dump_log',
)
def test_launch_jenkins_main_fail(monkeypatch):
    assert launch_jenkins.main() == 1


def test_launch_jenkins_version(monkeypatch, capsys):
    new_argv = [__file__, '--version']
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit) as e:
        launch_jenkins.main()
        assert int(e.value) == 0

    captured = capsys.readouterr()
    expect = 'Jenkins launcher v{}'.format(__version__)
    if sys.version_info < (3,):
        assert not captured.out
        assert captured.err.strip() == expect
    else:
        assert not captured.err
        assert captured.out.strip() == expect


def test_launch_jenkins_help(monkeypatch, capsys):
    new_argv = [__file__, '--help']
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit) as e:
        launch_jenkins.main()
        assert int(e.value) == 0

    captured = capsys.readouterr()
    out = captured.out.strip()

    assert 'Jenkins launcher' in out
    assert 'usage:' in out
    assert 'positional arguments:' in out
    assert 'optional arguments:' in out
