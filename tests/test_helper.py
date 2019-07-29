import time

from launch_jenkins import show_progress
from launch_jenkins import format_millis


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


def assert_progressbar_millis(capsys, millis=1100):
    """
    Call the `show_progress` function with the `millis` parameter and assert
    that a progress bar is shown with the associated time information.
    """
    msg = 'message'
    duration = 0.5
    show_progress(msg, duration, millis=millis)
    outerr = capsys.readouterr()
    print(outerr.err)
    assert msg in outerr.err
    assert '.' * 10 in outerr.err
    assert format_millis(millis + duration * 1000) in outerr.err
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


def raise_error(*args, **kwargs):
    raise RuntimeError
