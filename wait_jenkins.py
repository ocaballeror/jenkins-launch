"""
Launch a jenkins job and wait for it to finish.
"""
import re
import sys

from launch_and_wait import parse_args
from launch_and_wait import wait_for_job
from launch_and_wait import save_log_to_file


if __name__ == '__main__':
    launch_params = parse_args()
    build_url, auth, _ = launch_params
    if not re.search(r'/\d+/?$', build_url):
        raise ValueError("This url doesn't look like a valid build. Make sure \
there is a build number at the end.")
    response = wait_for_job(build_url, auth)
    result = wait_for_job(build_url, auth)
    save_log_to_file(build_url, auth)
    sys.exit(result)
