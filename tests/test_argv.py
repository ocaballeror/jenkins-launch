import sys

import pytest

from launch_jenkins import launch_jenkins
from launch_jenkins import parse_args

from .conftest import g_url, g_auth, g_params


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


@pytest.mark.parametrize(
    'args',
    [['--launch-only', '--wait-only']],
    ids=['Launch only and wait only'],
)
def test_parse_incompatible_args(monkeypatch, args):
    new_argv = ['python'] + g_params + args
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(SystemExit) as error:
        parse_args()
        assert 'not allowed with argument' in str(error.value)


def test_basic_argv(monkeypatch):
    new_argv = ['python'] + g_params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (g_url, g_auth, {})


def test_argv_params(monkeypatch):
    params = [
        'key=value',
        'keyt=other value',
        'empty=',
        'truth=1 == 0',
        's p a c e s = are cool',
    ]
    build_params = {
        'key': 'value',
        'keyt': 'other value',
        'empty': '',
        'truth': '1 == 0',
        's p a c e s': 'are cool',
    }
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    launch_params = parse_args()
    assert launch_params == (g_url, g_auth, build_params)


@pytest.mark.parametrize(
    'params', [['key'], ['key: value'], ['key=value', 'value: key']]
)
def test_argv_params_wrong_format(monkeypatch, params):
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    with pytest.raises(ValueError) as error:
        parse_args()
        assert 'use key=value format' in error.value


def test_optional_flags(monkeypatch, config):
    """
    Check that the known optional flags are accepted.
    """
    params = ['-q', '--dump', '--progress']
    new_argv = ['python'] + g_params + params
    monkeypatch.setattr(sys, 'argv', new_argv)
    parse_args()
    assert launch_jenkins.CONFIG['dump']
    assert launch_jenkins.CONFIG['quiet']
    assert launch_jenkins.CONFIG['progress']


@pytest.mark.parametrize(
    'arg, url, mode',
    [
        ('', g_url, 'full'),
        ('-l', g_url, 'launch'),
        ('-w', g_url + '/42', 'wait'),
    ],
    ids=['full', 'launch only', 'wait only'],
)
def test_launch_wait_only(arg, url, mode, monkeypatch, config):
    new_argv = ['python', '-j', url, '-u', g_auth[0], '-t', g_auth[1]]
    if arg:
        new_argv += [arg]
    monkeypatch.setattr(sys, 'argv', new_argv)
    parse_args()
    assert launch_jenkins.CONFIG['mode'] == mode
