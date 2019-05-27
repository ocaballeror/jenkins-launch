#!/usr/bin/env python
"""
Launch a jenkins job and wait for it to finish.
"""
import re
import sys

from launch_jenkins import parse_args
from launch_jenkins import parse_job_url
from launch_jenkins import wait_for_job
from launch_jenkins import save_log_to_file


def main():
    """
    Wait for a jenkins build to finish and retrieve its output.
    """
    launch_params = parse_args(verify_url=False)
    build_url, auth, _ = launch_params
    job_url, _, number = build_url.rstrip('/').rpartition('/')
    if not re.search(r'^\d+$', number):
        raise ValueError(
            "This url doesn't look like a valid build. Make sure \
there is a build number at the end."
        )
    parse_job_url(job_url)
    result = wait_for_job(build_url, auth)
    save_log_to_file(build_url, auth)
    return int(not result)


if __name__ == '__main__':
    sys.exit(main())
