import time

from launch_jenkins import show_progress
from launch_jenkins import format_millis


def assert_show_progressbar(capsys):
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


def assert_progressbar_millis(capsys, message, millis):
    """
    Capture stdout and assert that a progressbar has been shown with the
    specified message and milliseconds.
    """
    outerr = capsys.readouterr()
    assert message in outerr.err
    assert '.' * 10 in outerr.err
    assert format_millis(millis) in outerr.err
    assert not outerr.out


def assert_show_progressbar_millis(capsys, millis=1100):
    """
    Call the `show_progress` function with the `millis` parameter and assert
    that a progress bar is shown with the associated time information.
    """
    msg = 'message'
    duration = 0.5
    show_progress(msg, duration, millis=millis)
    assert_progressbar_millis(capsys, msg, millis + duration * 1000)


def assert_show_no_progressbar(capsys):
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


def assert_show_empty_progress(capsys):
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
