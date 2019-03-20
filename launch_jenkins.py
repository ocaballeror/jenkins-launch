"""
Launch a jenkins job and wait for it to finish.
"""
from launch_and_wait import parse_args
from launch_and_wait import launch_build
from launch_and_wait import wait_queue_item


if __name__ == '__main__':
    launch_params = parse_args()
    auth = launch_params[1]
    location = launch_build(*launch_params)
    build_url = wait_queue_item(location, auth)
    print(build_url)
