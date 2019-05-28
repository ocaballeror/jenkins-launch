from launch_jenkins import launch_jenkins
from launch_jenkins import log
from launch_jenkins import errlog


def test_log(monkeypatch, capsys):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', False)
    log('hello', 'world')
    out, err = capsys.readouterr()
    assert not out
    assert err == 'hello world\n'

    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', True)
    log('hello', 'world')
    out, err = capsys.readouterr()
    assert not out
    assert not err


def test_errlog(monkeypatch, capsys):
    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', False)
    errlog('hello', 'world')
    out, err = capsys.readouterr()
    assert not out
    assert err == 'hello world\n'

    monkeypatch.setitem(launch_jenkins.CONFIG, 'quiet', True)
    errlog('hello', 'world')
    out, err = capsys.readouterr()
    assert not out
    assert err == 'hello world\n'
