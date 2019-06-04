from launch_jenkins import launch_jenkins
from launch_jenkins import log
from launch_jenkins import errlog
from launch_jenkins import CaseInsensitiveDict


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


def test_caseinsensitivedict():
    cid = CaseInsensitiveDict()
    cid['key'] = 'value'
    cid['other'] = 'othervalue'
    del cid['other']
    assert cid['key'] == cid['KEY']
    assert list(cid) == ['key']
    assert len(cid) == 1
    assert cid == {'key': 'value'}
    assert cid.copy() == cid
    assert cid != 'somethingelse'
    assert repr(cid)
