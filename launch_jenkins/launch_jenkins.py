#!/usr/bin/env python
"""
Launch a jenkins job and wait for it to finish.
"""
import sys
from launch_jenkins import parse_args
from launch_jenkins import launch_build
from launch_jenkins import wait_queue_item


def main():
    """
    Launch the jenkins job and print the build url to stdout.
    """
    launch_params = parse_args()
    auth = launch_params[1]
    location = launch_build(*launch_params)
    build_url = wait_queue_item(location, auth)
    print(build_url)


if __name__ == '__main__':
    sys.exit(main())
