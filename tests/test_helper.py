import time
from launch_and_wait import show_progress


def assert_progressbar(capsys):
    """
    Call the `show_progress` function and assert that a progress bar is shown.
    """
    msg = 'message'
    t0 = time.time()
    show_progress(msg, 0.5)
    outerr = capsys.readouterr()
    assert time.time() - t0 >= 0.5
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
    assert time.time() - t0 >= 0.5
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
    assert time.time() - t0 >= 0.5
    assert not outerr.err
    assert not outerr.out
