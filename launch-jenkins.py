import json
import sys
import time
import os
from itertools import cycle

import requests


hostname = ''
job_name = ''

username = ''
pwd = ''
auth = (username, pwd)

build = '/build' if len(sys.argv) == 1 else '/buildWithParameters'
actual_jobname = '/job/'.join(('/' + job_name).split('/'))


def show_progress(msg, duration):
    """
    Show a message and a progress bar for the specified amount of time.

    Note that you need to print a newline manually if you intend to post any
    other message to stdout.
    """
    bar = cycle(['|', '/', '-', '\\'])
    msg += '  '
    elapsed = 0
    while elapsed < duration:
        spaces = os.get_terminal_size().columns - len(msg) - 3
        spaces = max(spaces, 40)
        out = '{}{}  {}'.format(msg, '.' * spaces, next(bar))
        print(out, end='\r')
        time.sleep(0.1)
        elapsed += 0.1


def launch_build():
    """
    Submit job and return the queue item location.
    """
    url = hostname + actual_jobname + build
    print('Sending build request')
    params = {k: v for k, v in map(lambda f: f.split('='), sys.argv[1:])}
    print(params)
    response = requests.post(url, params=params, auth=auth)
    location = response.headers['Location']

    assert 'queue' in location, \
        'Err: Something went wrong with the Jenkins API'
    return location


def wait_queue_item(location):
    """
    Wait until the item starts building.
    """
    queue = location + 'api/json'
    while True:
        response = requests.get(queue, auth=auth).json()
        if response.get('cancelled', False):
            print('Err: Build was cancelled', file=sys.stderr)
            sys.exit(1)
        if response.get('executable', False):
            build_url = response['executable']['url']
            break
        show_progress('Job queued', 5)
    print('')
    return build_url


def wait_for_job(build_url):
    """
    Wait until the build finishes.
    """
    poll_url = build_url + 'api/json'
    while True:
        response = requests.get(poll_url, auth=auth).json()
        msg = 'Build %s in progress' % response['displayName']
        show_progress(msg, 5)
        if response.get('result', False):
            print('\nThe job ended in', response['result'])
            break
    return response


def save_log_to_file(build_url, displayName):
    """
    Save the build log to a file.
    """
    filename = (job_name + displayName).replace('/', '_')
    log_file = '/tmp/%s.txt' % filename
    url = build_url + 'consoleText'
    console_log = requests.get(url, auth=auth, stream=True)
    console_log.raise_for_status()
    with open(log_file, 'wb') as file:
        for block in console_log.iter_content(2048):
            file.write(block)
    print('Job output saved to', log_file)


if __name__ == '__main__':
    g_location = launch_build()
    g_build_url = wait_queue_item(g_location)
    g_response = wait_for_job(g_build_url)
    save_log_to_file(g_build_url, g_response['displayName'])
