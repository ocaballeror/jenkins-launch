"""
Launch a jenkins job and wait for it to finish.
"""
import argparse
import json
import sys
import time
import os
from itertools import cycle

import requests


def parse_args():
    """
    Parse command line arguments and return a tuple with the relevant
    parameters. The tuple will be of type (url, auth, params), with the full
    url to launch the job, the authentication tuple for the requests package
    and the build parameters for the job, if any.
    """
    parser = argparse.ArgumentParser(
        description='Launch a Jenkins job and wait for it to finish'
    )
    parser.add_argument('-u', '--user', help='Username', type=str,
        required=True)
    parser.add_argument('-t', '--token', help='User token', type=str,
        required=True)
    parser.add_argument(
        '-j', '--job', help='The full url of the job to launch', type=str,
        required=True
    )
    parser.add_argument(
        'params',
        help='(Optional) A list of parameters in the form key=value',
        nargs='*',
    )
    args = parser.parse_args()

    params = {k: v for k, v in map(lambda f: f.split('='), args.params)}
    return (args.job, (args.user, args.token), params)


def show_progress(msg, duration):
    """
    Show a message and a progress bar for the specified amount of time.

    Note that you need to print a newline manually if you intend to post any
    other message to stdout.
    """
    bar = cycle(['|', '/', '-', '\\'])
    progress = (sys.stdout.isatty() and sys.platform != 'win32')
    if not progress:
        print(msg + '...')

    msg += '  '
    elapsed = 0
    while elapsed < duration:
        if progress:
            spaces = os.get_terminal_size(0).columns - len(msg) - 3
            spaces = max(spaces, 40)
            out = '{}{}  {}'.format(msg, '.' * spaces, next(bar))
            print(out, end='\r')
        time.sleep(0.1)
        elapsed += 0.1


def is_parametrized(url, auth):
    """
    Determine if the build is parametrized or not.
    """
    if url[-1] != '/':
        url += '/'
    url += 'api/json'
    response = requests.get(url, auth=auth)
    if response.status_code >= 400:
        print(json.dumps(dict(response.headers), indent=4), file=sys.stderr)
        print(response.text, file=sys.stderr)
        raise RuntimeError

    response = response.json()
    props = response.get('property', False)
    if not props:
        return False
    return any('parameterDefinitions' in prop for prop in props)


def launch_build(url, auth, params=None):
    """
    Submit job and return the queue item location.
    """
    if url[-1] != '/':
        url += '/'
    has_params = bool(params) or is_parametrized(url, auth)
    url += ('buildWithParameters' if has_params else 'build')
    print('Sending build request')
    response = requests.post(url, params=params, auth=auth)
    if response.status_code >= 400:
        print(json.dumps(dict(response.headers), indent=4), file=sys.stderr)
        print(response.text, file=sys.stderr)
        raise RuntimeError

    assert 'location' in response.headers, \
        'Err: Something went wrong with the Jenkins API'
    location = response.headers['Location']

    assert ('queue' in location), \
        'Err: Something went wrong with the Jenkins API'
    return location


def wait_queue_item(location, auth, interval=5.):
    """
    Wait until the item starts building.
    """
    if location[-1] != '/':
        location += '/'
    queue = location + 'api/json'
    while True:
        response = requests.get(queue, auth=auth).json()
        if response.get('cancelled', False):
            print('Err: Build was cancelled', file=sys.stderr)
            sys.exit(1)
        if response.get('executable', False):
            build_url = response['executable']['url']
            break
        show_progress('Job queued', interval)
    print('')
    return build_url


def wait_for_job(build_url, auth, interval=5.):
    """
    Wait until the build finishes.
    """
    if build_url[-1] != '/':
        build_url += '/'
    poll_url = build_url + 'api/json'
    while True:
        response = requests.get(poll_url, auth=auth).json()
        msg = 'Build %s in progress' % response['displayName']
        show_progress(msg, interval)
        if response.get('result', False):
            print('\nThe job ended in', response['result'])
            break
    return response


def save_log_to_file(build_url, auth):
    """
    Save the build log to a file.
    """
    if build_url[-1] != '/':
        build_url += '/'
    job_name = build_url[build_url.find('/job/'):]
    job_name = job_name.replace('/', '_').replace('_job_', '_').strip('_')
    log_file = job_name + '.txt'
    url = build_url + 'consoleText'
    console_log = requests.get(url, auth=auth, stream=True)
    console_log.raise_for_status()
    with open(log_file, 'wb') as file:
        for block in console_log.iter_content(2048):
            file.write(block)
    print('Job output saved to', log_file)


if __name__ == '__main__':
    launch_params = parse_args()
    g_auth = launch_params[1]
    g_location = launch_build(*launch_params)
    g_build_url = wait_queue_item(g_location, g_auth)
    g_response = wait_for_job(g_build_url, g_auth)
    save_log_to_file(g_build_url, g_auth)
