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
import ssl
import functools
import warnings
from itertools import cycle
from collections import namedtuple
from collections import OrderedDict

if sys.version_info >= (3,):
    from urllib.request import Request, HTTPCookieProcessor  # noqa:F401
    from urllib.request import urlopen, urlsplit, install_opener
    from urllib.request import build_opener  # noqa:F401
    from urllib.error import HTTPError  # noqa:F401
    from urllib.parse import urlencode  # noqa:F401
    from collections.abc import Mapping, MutableMapping  # noqa:F401
    from http.cookiejar import CookieJar  # noqa:F401
else:
    from urllib2 import Request, HTTPError, HTTPCookieProcessor  # noqa:F401
    from urllib2 import urlopen, build_opener, install_opener  # noqa:F401
    from urllib import urlencode  # noqa:F401
    from urlparse import urlsplit  # noqa:F401
    from collections import Mapping, MutableMapping  # noqa:F401
    from cookielib import CookieJar  # noqa:F401


CONFIG = {
    'dump': False,
    'quiet': False,
    'progress': False,
    'mode': 'full',
    'debug': False,
    'verify_ssl': True,
}
__version__ = '2.2.2'


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

    key, value = kwarg.split('=', 1)
    return key.strip(), value.strip()


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

    job = parse_job_url(args.job, has_number=args.wait_only)
    try:
        params = {k: v for k, v in map(parse_kwarg, args.params)}
    except Exception as error:
        msg = str(error) or 'Job arguments are not properly formatted'
        raise ValueError(msg)
    return (job, (args.user, args.token), params)


def parse_job_url(job, has_number=False):
    """
    Parse the user input job url and return it along with a list of parameters.
    """
    job = job.rstrip('/')

    if has_number:
        job_url, _, number = job.rstrip('/').rpartition('/')
        if number != 'lastBuild' and not re.search(r'^\d+$', number):
            raise ValueError(
                "This url doesn't look like a valid build. Make sure "
                "there is a build number at the end."
            )
    else:
        action = re.search('^(.*)/build(WithParameters)?$', job)
        if action:
            job = action.group(1)
        if not re.search(r'/job/[^/]+$', job):
            raise ValueError('Invalid job URL')

    if not re.search('https?://[^/]+(/job/[^/])+', job):
        raise ValueError('Invalid job URL')

    return job


def get_stderr_size_unix():
    """
    Get the size in rows and columns of the current STDERR.
    """
    if hasattr(os, 'get_terminal_size'):
        return os.get_terminal_size(2)

    Size = namedtuple('Size', 'lines columns')
    output = os.popen('stty size -F /dev/stderr', 'r').read().split()
    if len(output) != 2:
        raise OSError(' '.join(output))
    lines, columns = output
    return Size(lines=int(lines), columns=int(columns))


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


def format_millis(millis):
    """
    Format milliseconds as mm:ss.
    """
    millis = int(millis / 1000)
    if millis >= 3600:
        formatted = '%d:%02d:%02d' % (
            millis / 3600,
            (millis % 3600) / 60,
            (millis % 3600) % 60,
        )
    else:
        formatted = '%02d:%02d' % (millis / 60, millis % 60)

    return formatted


def show_progress(msg, duration, millis=None):
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

    msg = msg.strip() + ' '
    out_msg = msg
    elapsed = 0
    while elapsed < duration:
        if millis is not None:
            out_msg = '[{}] {}'.format(format_millis(millis), msg)
            millis += 100

        spaces = get_stderr_size_unix().columns - len(out_msg) - 3
        spaces = max(spaces, 40)
        out = '{}{}  {}'.format(out_msg, '.' * spaces, next(bar))
        log(out, end='\r')
        time.sleep(0.1)
        elapsed += 0.1


def deprecate(instead):
    """
    Issue a deprecation warning about this method and call another one instead.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            other = instead
            ismethod = len(args) > 0 and hasattr(args[0], func.__name__)
            # if the decorated function is a method, try to find another
            # method named "other" in the same object
            if ismethod and hasattr(args[0], other):
                other = getattr(args[0], other)
            else:
                other = globals()[other]
            # if it's a method, remove self from the args list
            if ismethod:
                args = args[1:]
            msg = (
                '{} is deprecated and will be removed in the next major '
                'version. Please use {} instead'
            )
            msg = msg.format(func.__name__, other.__name__)
            warnings.warn(msg, DeprecationWarning)
            func.__doc__ = other.__doc__
            return other(*args, **kwargs)

        return wrapper
    return decorator


def stream_response(response):
    while True:
        response.text = response.read(8192)
        if not response.text:
            break
        yield response


def init_ssl():
    """
    Create an SSL context and load certificates from the system's directory.
    """
    context = ssl.create_default_context()
    if CONFIG['verify_ssl']:
        ca_dir = os.environ.get('SSL_CERT_DIR', '/etc/ssl/certs')
        ca_file = os.environ.get('SSL_CERT_FILE', None)
        if not ca_file:
            bundles = [
                '/etc/ssl/certs/ca-bundle.crt',
                '/etc/ssl/certs/ca-certificates.crt',
            ]
            for bundle in bundles:
                if os.path.exists(bundle):
                    ca_file = bundle
        context.load_verify_locations(ca_file, ca_dir, None)
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context


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
        if str(value) not in choices:
            msg = "Invalid choice '{}' for parameter '{}'."
            msg += "\n\nValid choices are {}"
            raise ValueError(msg.format(value, key, choices))


class Session:
    def __init__(self, base, auth=None):
        self.auth = auth
        self.headers = {'User-Agent': 'foobar'}
        self.context = init_ssl()
        self.jar = CookieJar()
        split = urlsplit(base)
        self.base = '{}://{}'.format(split.scheme, split.netloc)

        if self.auth:
            auth = ':'.join(self.auth)
            if sys.version_info >= (3,):
                basic = base64.b64encode(auth.encode('ascii')).decode('ascii')
            else:
                basic = base64.b64encode(auth)
            self.headers['Authorization'] = 'Basic {}'.format(basic)

        self._get_crumb()

    def _get_crumb(self):
        """
        Get the necessary crumb header if our Jenkins instance is CSRF
        protected, and automatically add it to this session's default headers.
        """
        try:
            args = 'xpath=concat(//crumbRequestField,":",//crumb)'
            resp = self.get_url(self.base + '/crumbIssuer/api/xml?' + args)
        except HTTPError as err:
            if err.code != 404:
                raise
        else:
            key, value = resp.text.split(':')
            self.headers[key] = value

    def get_url(self, url, data=None, stream=False, retries=5):
        headers = self.headers.copy()
        if data is not None:
            data = urlencode(data).encode('utf-8')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            retries = 1  # do not retry POSTs
        req = Request(url, data, headers=headers)
        self.jar.add_cookie_header(req)
        for i in range(retries):  # pragma: nocover
            try:
                response = urlopen(req, context=self.context)
            except HTTPError:
                if i == retries - 1:
                    raise
                time.sleep(0.1)
            else:
                break
        self.jar.extract_cookies(response, req)
        if sys.version_info >= (3,):
            response.headers = CaseInsensitiveDict(response.headers._headers)
        else:
            response.headers = CaseInsensitiveDict(response.headers.dict)
        if stream:
            return stream_response(response)
        else:
            response.text = response.read().decode('utf-8')
            return response

    def get_job_params(self, url):
        """
        Get the list of allowed parameters and their respective choices.
        """
        url = url.rstrip('/') + '/api/json'
        response = self.get_url(url)
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

    def launch_build(self, url, params=None):
        """
        Submit job and return the queue item location.
        """
        url = url.rstrip('/') + '/'
        job_params = self.get_job_params(url)
        validate_params(job_params, params)

        url += 'buildWithParameters' if job_params else 'build'
        url += '?delay=0'
        log('Sending build request')
        data = params or ""  # urllib will send a POST with an empty string
        response = self.get_url(url, data=data)

        assert (
            'Location' in response.headers
        ), 'Something went wrong with the Jenkins API'
        location = response.headers['Location']

        assert 'queue' in location, 'Something went wrong with the Jenkins API'
        return location

    def get_queue_status(self, location):
        """
        Check the status of a queue item. Returns the build url if the job is
        already executing, or None if it's still in the queue.
        """
        queue = location.rstrip('/') + '/api/json'
        response = self.get_url(queue)
        response = json.loads(response.text)
        if response.get('cancelled', False):
            raise RuntimeError('Build was cancelled')
        if response.get('executable', False):
            return response['executable']['url']
        return None

    @deprecate(instead='wait_queue')
    def wait_queue_item(self, *args, **kwargs):
        pass

    def wait_queue(self, location, interval=5.0):
        """
        Wait until the item starts building.
        """
        while True:
            job_url = self.get_queue_status(location)
            if job_url is not None:
                break
            show_progress('Job queued', interval)
        log('')
        return job_url

    @deprecate(instead='job_status')
    def get_job_status(self, *args, **kwargs):
        pass

    def job_status(self, build_url):
        """
        Check the status of a running build.

        Returns a tuple with the status of the build and the current stage.
        The status is True on successful exit, False on failure or None if the
        build is still running.
        """
        poll_url = build_url.rstrip('/') + '/wfapi/describe'
        try:
            response = self.get_url(poll_url)
        except HTTPError as error:
            if error.code == 404:
                build_number = build_url.rstrip('/').rpartition('/')[2]
                error.msg = 'Build #%s does not exist' % build_number
            raise
        response = json.loads(response.text)

        status = response.get('status', '')
        stages = response.get('stages', [{}])
        if status == 'NOT_EXECUTED':
            if response.get('durationMillis', 0) == 0:
                # Build has just been launched. Report it as in_progress
                return None, {}
            # Build finished as not_executed. Probably an in your Jenkinsfile
            return False, stages[-1]
        elif status == 'IN_PROGRESS':
            in_progress = [
                s for s in stages if s.get('status', '') == 'IN_PROGRESS'
            ]
            in_progress = in_progress or [{}]
            return None, in_progress[0]
        else:
            # Jenkins returns false negatives in the 'status' field sometimes.
            # Instead of trusting 'status', we will determine if the build
            # failed by checking if any of the stages failed.
            last = stages[-1]
            status = all(
                s.get('status', '') in ('SUCCESS', 'NOT_EXECUTED')
                for s in stages
            )
            return status, last

    @deprecate(instead='wait_job')
    def wait_for_job(self, *args, **kwargs):
        pass

    def wait_job(self, build_url, interval=5.0):
        """
        Wait until the build finishes.
        """
        name = '#' + build_url.rstrip('/').split('/')[-1]
        last_stage = None
        while True:
            status, stage = self.job_status(build_url)
            if status is not None:
                status_name = 'SUCCESS' if status else 'FAILURE'
                log('\nJob', name, 'ended in', status_name)
                return status

            stage_name = stage.get('name', '')
            msg = stage_name or 'Build %s in progress' % name
            millis = stage.get('durationMillis', None)
            if stage_name != last_stage:
                last_stage = stage_name
                msg = '\n' + msg
            show_progress(msg, interval, millis=millis)

    def retrieve_log(self, build_url):
        """
        Get the build log and return it as a string.
        """
        build_url = build_url.rstrip('/') + '/'
        url = build_url + 'consoleText'
        log = ''.join(
            block.text.decode('utf-8', errors='ignore')
            for block in self.get_url(url, stream=True)
        )
        return log

    @deprecate(instead='dump_log')
    def save_log_to_file(self, *args, **kwargs):
        pass

    def dump_log(self, build_url):
        """
        Save the build log to a file.
        """
        build_url = build_url.rstrip('/') + '/'
        if CONFIG['dump']:
            file = sys.stdout
        else:
            job_name = build_url[build_url.find('/job/') :]
            job_name = (
                job_name.replace('/', '_').replace('_job_', '_').strip('_')
            )
            log_file = job_name + '.txt'
            file = io.open(log_file, 'w', encoding='utf-8')

        file.write(self.retrieve_log(build_url))

        if not CONFIG['dump']:
            file.close()
            log('Job output saved to', log_file)


def launch_build(url, auth, *args, **kwargs):
    return Session(url, auth).launch_build(url, *args, **kwargs)


@deprecate(instead='wait_queue')
def wait_queue_item(*args, **kwargs):
    pass


def wait_queue(url, auth, *args, **kwargs):
    return Session(url, auth).wait_queue_item(url, *args, **kwargs)


@deprecate(instead='wait_job')
def wait_for_job(*args, **kwargs):
    pass


def wait_job(url, auth, *args, **kwargs):
    return Session(url, auth).wait_for_job(url, *args, **kwargs)


@deprecate(instead='dump_log')
def save_log_to_file(*args, **kwargs):
    pass


def dump_log(url, auth, *args, **kwargs):
    return Session(url, auth).save_log_to_file(url, *args, **kwargs)


def main():
    """
    Launch a Jenkins build and wait for it to finish.
    """
    launch_params = parse_args()
    build_url, auth, params = launch_params
    session = Session(build_url, auth)

    if CONFIG['mode'] != 'wait':
        location = session.launch_build(build_url, params)
        build_url = session.wait_queue(location)

    if CONFIG['mode'] == 'launch':
        print(build_url)
        return 0

    result = session.wait_job(build_url)
    session.dump_log(build_url)
    return int(not result)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        if CONFIG['debug']:
            raise
        errlog('Err:', e)
        sys.exit(1)
