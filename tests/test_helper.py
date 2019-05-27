import os
import time
from collections import namedtuple

import pytest

from launch_jenkins import show_progress


def assert_progressbar(capsys):
    """
    Call the `show_progress` function and assert that a progress bar is shown.
    """
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.4
    assert msg in outerr.err
    assert '.' * 10 in outerr.err
    assert not outerr.out


def assert_no_progressbar(capsys):
    """
    Call the `show_progress` function and assert that no progress bar is shown,
    but the message is printed in its simple form.
    """
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.4
    assert outerr.err == '{}...\r'.format(msg)
    assert not outerr.out


def assert_empty_progress(capsys):
    """
    Call the `show_progress` function and assert that nothing is printed to
    either stderr or stdout.
    """
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.4
    assert not outerr.err
    assert not outerr.out


@pytest.fixture(scope='function')
def terminal_size(monkeypatch):
    """
    Set a fake os.get_terminal_size() function that returns (30, 30).
    """

    def fake_terminal_size(*args, **kwargs):
        return Size(30, 30)

    Size = namedtuple('terminal_size', 'columns rows')
    has_func = hasattr(os, 'get_terminal_size')
    if not has_func:
        os.get_terminal_size = fake_terminal_size
    else:
        monkeypatch.setattr(os, 'get_terminal_size', fake_terminal_size)
    yield

    if not has_func:
        del os.get_terminal_size


def raise_error(*args, **kwargs):
    raise RuntimeError
