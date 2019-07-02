#!/usr/bin/env python
"""
Launch a jenkins job and wait for it to finish.
"""
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import argparse
import json
import sys
import time
import os
import re
import base64
import io
from itertools import cycle
from collections import namedtuple
from collections import OrderedDict

if sys.version_info >= (3,):
    from urllib.request import Request, urlopen  # noqa:F401
    from urllib.error import HTTPError  # noqa:F401
    from urllib.parse import urlencode  # noqa:F401
    from collections.abc import Mapping, MutableMapping  # noqa:F401
else:
    from urllib2 import Request, urlopen  # noqa:F401
    from urllib2 import HTTPError  # noqa:F401
    from urllib import urlencode  # noqa:F401
    from collections import Mapping, MutableMapping  # noqa:F401


CONFIG = {
    'dump': False,
    'quiet': False,
    'progress': False,
    'mode': 'full',
    'debug': False,
}

__version__ = '2.1.3'


class CaseInsensitiveDict(MutableMapping):
    """
    A case-insensitive ``dict``-like object.

    Implements all methods and operations of
    ``MutableMapping`` as well as dict's ``copy``. Also
    provides ``lower_items``.

    All keys are expected to be strings. The structure remembers the
    case of the last key to be set, and ``iter(instance)``,
    ``keys()``, ``items()``, ``iterkeys()``, and ``iteritems()``
    will contain case-sensitive keys. However, querying and contains
    testing is case insensitive::

        cid = CaseInsensitiveDict()
        cid['Accept'] = 'application/json'
        cid['aCCEPT'] == 'application/json'  # True
        list(cid) == ['Accept']  # True

    For example, ``headers['content-encoding']`` will return the
    value of a ``'Content-Encoding'`` response header, regardless
    of how the header name was originally stored.

    If the constructor, ``.update``, or equality comparison
    operations are given keys that have equal ``.lower()``s, the
    behavior is undefined.
    """

    def __init__(self, data=None, **kwargs):
        self._store = OrderedDict()
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key, value):
        # Use the lowercased key for lookups, but store the actual
        # key alongside the value.
        self._store[key.lower()] = (key, value)

    def __getitem__(self, key):
        return self._store[key.lower()][1]

    def __delitem__(self, key):
        del self._store[key.lower()]

    def __iter__(self):
        return (casedkey for casedkey, mappedvalue in self._store.values())

    def __len__(self):
        return len(self._store)

    def lower_items(self):
        """Like iteritems(), but with all lowercase keys."""
        return (
            (lowerkey, keyval[1]) for (lowerkey, keyval) in self._store.items()
        )

    def __eq__(self, other):
        if not isinstance(other, Mapping):
            return False
        # Compare insensitively
        other = CaseInsensitiveDict(other)
        return dict(self.lower_items()) == dict(other.lower_items())

    # Copy is required
    def copy(self):
        return CaseInsensitiveDict(self._store.values())

    def __repr__(self):
        return str(dict(self.items()))


def log(*args, **kwargs):
    if CONFIG['quiet']:
        return
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


def errlog(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


def parse_kwarg(kwarg):
    """
    Parse a key=value argument from the command line and return it as a
    (key, value) tuple.
    """
    count = kwarg.count('=')
    if count == 0:
        msg = 'Invalid job argument: "{}". Please use key=value format'
        raise ValueError(msg.format(kwarg))

    if count == 1 and kwarg.endswith('='):
        return kwarg[:-1], ''
    return kwarg.split('=', 1)


def parse_args():
    """
    Parse command line arguments and return a tuple with the relevant
    parameters. The tuple will be of type (url, auth, params), with the full
    url to launch the job, the authentication tuple for the requests package
    and the build parameters for the job, if any.
    """
    parser = argparse.ArgumentParser(
        prog='Jenkins launcher',
        description='Launch a Jenkins job and wait for it to finish',
    )
    parser.add_argument(
        '-u', '--user', help='Username', type=str, required=True
    )
    parser.add_argument(
        '-t', '--token', help='User token', type=str, required=True
    )
    parser.add_argument(
        '-j',
        '--job',
        help='The full url of the job to launch',
        type=str,
        required=True,
    )
    parser.add_argument(
        '--dump', help='Print job output to stdout', action='store_true'
    )
    parser.add_argument(
        '--debug', help='Print debug output', action='store_true'
    )
    parser.add_argument(
        '-q', '--quiet', help='Do not print user messages', action='store_true'
    )
    parser.add_argument(
        '-p', '--progress', help='Force show progress bar', action='store_true'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s v{}'.format(__version__),
    )
    parser.add_argument(
        'params',
        help='(Optional) A list of parameters in the form key=value',
        nargs='*',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-l',
        '--launch-only',
        help='Only launch the build. Exit when it starts running',
        action='store_true',
    )
    group.add_argument(
        '-w',
        '--wait-only',
        help='Interpret the job url as an already running build '
        'and wait for it to finish',
        action='store_true',
    )
    args = parser.parse_args()

    CONFIG['dump'] = args.dump
    CONFIG['quiet'] = args.quiet
    CONFIG['progress'] = args.progress
    CONFIG['debug'] = args.debug
    if args.launch_only:
        CONFIG['mode'] = 'launch'
    elif args.wait_only:
        CONFIG['mode'] = 'wait'

    if not args.wait_only:
        job, params = parse_job_url(args.job)
        params += args.params
    else:
        job, params = args.job, args.params

    try:
        params = {k: v for k, v in map(parse_kwarg, params)}
    except Exception as error:
        msg = str(error) or 'Job arguments are not properly formatted'
        raise ValueError(msg)
    return (job, (args.user, args.token), params)


def parse_build_url(url):
    """
    Get the job url from a build url. Raise a ValueError if the build url
    appears to be malformed.
    """
    job_url, _, number = url.rstrip('/').rpartition('/')
    if not re.search(r'^\d+$', number):
        raise ValueError(
            "This url doesn't look like a valid build. Make sure \
there is a build number at the end."
        )
    return job_url


def parse_job_url(job):
    """
    Parse the user input job url and return it along with a list of parameters.
    """
    job = job.rstrip('/')
    if re.search(r'/job/[^/]*$', job):
        return job, []

    url = re.search('^(.*)/build$', job)
    if url:
        return url.group(1), []

    url = re.search(r'^(.*)/buildWithParameters\??(.*)$', job)
    if url:
        args = url.group(2).split('&')
        if args == ['']:
            args = []
        return url.group(1), args

    raise ValueError('Invalid job URL')


def get_stderr_size_unix():
    """
    Get the size in rows and columns of the current STDERR.
    """
    if hasattr(os, 'get_terminal_size'):
        return os.get_terminal_size(2)

    Size = namedtuple('Size', 'rows columns')
    output = os.popen('stty size -F /dev/stderr', 'r').read().split()
    if len(output) != 2:
        raise OSError(' '.join(output))
    rows, columns = output
    return Size(rows=int(rows), columns=int(columns))


def is_progressbar_capable():
    """
    Determine whether the current system is capable of showing the progress bar
    or not.
    """
    progress = sys.stderr.isatty() and sys.platform != 'win32'
    progress |= CONFIG['progress']
    try:
        get_stderr_size_unix()
    except Exception:
        return False
    return progress


def show_progress(msg, duration):
    """
    Show a message and a progress bar for the specified amount of time.

    Note that you need to print a newline manually if you intend to post any
    other message to stdout.
    """
    bar = cycle(['|', '/', '-', '\\'])
    progress = is_progressbar_capable()
    if not progress:
        log(msg + '...', end='\r')
        time.sleep(duration)
        return

    msg += '  '
    elapsed = 0
    while elapsed < duration:
        spaces = get_stderr_size_unix().columns - len(msg) - 3
        spaces = max(spaces, 40)
        out = '{}{}  {}'.format(msg, '.' * spaces, next(bar))
        log(out, end='\r')
        time.sleep(0.1)
        elapsed += 0.1


def stream_response(response):
    while True:
        response.text = response.read(8192)
        if not response.text:
            break
        yield response


def get_url(url, auth, data=None, stream=False):
    headers = {'User-Agent': 'foobar'}
    auth = ':'.join(auth)
    if sys.version_info >= (3,):
        basic = base64.b64encode(auth.encode('ascii')).decode('ascii')
    else:
        basic = base64.b64encode(auth)
    headers['Authorization'] = 'Basic {}'.format(basic)

    if data is not None:
        data = urlencode(data).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = Request(url, data, headers=headers)
    response = urlopen(req)
    if sys.version_info >= (3,):
        response.headers = CaseInsensitiveDict(response.headers._headers)
    else:
        response.headers = CaseInsensitiveDict(response.headers.dict)
    if stream:
        return stream_response(response)
    else:
        response.text = response.read().decode('utf-8')
        return response


def get_job_params(url, auth):
    """
    Get the list of allowed parameters and their respective choices.
    """
    url = url.rstrip('/') + '/api/json'
    response = get_url(url, auth=auth)
    response = json.loads(response.text)
    props = response.get('property', [])
    definition_prop = 'hudson.model.ParametersDefinitionProperty'
    defs = next(
        (
            p['parameterDefinitions']
            for p in props
            if p.get('_class', '') == definition_prop
        ),
        [],
    )
    if not defs:
        return {}

    params = {}
    for definition in defs:
        params[definition['name']] = definition.get('choices', None)
    return params


def validate_params(definitions, supplied):
    """
    Check the dict of supplied params against the list of allowed choices.
    """
    if not supplied:
        return True

    if supplied and not definitions:
        raise ValueError('This build does not take any parameters')

    nonexistent = [p for p in supplied if p not in definitions]
    if nonexistent:
        nonexistent = ', '.join(nonexistent)
        raise ValueError('These parameters do not exist:', nonexistent)

    for key, value in supplied.items():
        choices = definitions[key]
        if choices is None:
            continue
        if value not in choices:
            raise ValueError(
                "Invalid choice '{}' for parameter '{}'".format(value, key)
            )


def launch_build(url, auth, params=None):
    """
    Submit job and return the queue item location.
    """
    url = url.rstrip('/') + '/'
    job_params = get_job_params(url, auth)
    validate_params(job_params, params)

    url += 'buildWithParameters' if job_params else 'build'
    log('Sending build request')
    data = params or ""  # urllib will send a POST with an empty string
    response = get_url(url, data=data, auth=auth)

    assert (
        'Location' in response.headers
    ), 'Something went wrong with the Jenkins API'
    location = response.headers['Location']

    assert 'queue' in location, 'Something went wrong with the Jenkins API'
    return location


def wait_queue_item(location, auth, interval=5.0):
    """
    Wait until the item starts building.
    """
    queue = location.rstrip('/') + '/api/json'
    while True:
        response = get_url(queue, auth=auth)
        response = json.loads(response.text)
        if response.get('cancelled', False):
            errlog('Build was cancelled', file=sys.stderr)
            sys.exit(1)
        if response.get('executable', False):
            build_url = response['executable']['url']
            break
        show_progress('Job queued', interval)
    log('')
    return build_url


def wait_for_job(build_url, auth, interval=5.0):
    """
    Wait until the build finishes.
    """
    ret = 0
    poll_url = build_url.rstrip('/') + '/api/json'
    try:
        response = get_url(poll_url, auth=auth)
    except HTTPError as error:
        if error.code == 404:
            build_number = build_url.rstrip('/').rpartition('/')[2]
            error.msg = 'Build #%s does not exist' % build_number
        raise error

    response = json.loads(response.text)
    while True:
        if response.get('result', False):
            result = response['result']
            log('\nThe job ended in', response['result'])
            ret = result.lower() == 'success'
            break
        msg = 'Build %s in progress' % response['displayName']
        show_progress(msg, interval)
        response = get_url(poll_url, auth=auth)
        response = json.loads(response.text)
    return ret


def save_log_to_file(build_url, auth):
    """
    Save the build log to a file.
    """
    build_url = build_url.rstrip('/') + '/'
    if CONFIG['dump']:
        file = sys.stdout
    else:
        job_name = build_url[build_url.find('/job/') :]
        job_name = job_name.replace('/', '_').replace('_job_', '_').strip('_')
        log_file = job_name + '.txt'
        file = io.open(log_file, 'w', encoding='utf-8')

    url = build_url + 'consoleText'
    for block in get_url(url, auth=auth, stream=True):
        file.write(block.text.decode('utf-8', errors='ignore'))

    if not CONFIG['dump']:
        file.close()
        log('Job output saved to', log_file)


def main():
    """
    Launch a Jenkins build and wait for it to finish.
    """
    launch_params = parse_args()
    build_url, auth, _ = launch_params

    if CONFIG['mode'] == 'wait':
        job_url = parse_build_url(build_url)
        parse_job_url(job_url)
    else:
        location = launch_build(*launch_params)
        build_url = wait_queue_item(location, auth)

    if CONFIG['mode'] == 'launch':
        print(build_url)
        return 0

    result = wait_for_job(build_url, auth)
    save_log_to_file(build_url, auth)
    return int(not result)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        if CONFIG['debug']:
            raise
        errlog('Err:', e)
        sys.exit(1)
