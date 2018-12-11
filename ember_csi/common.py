# Copyright (c) 2018, Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from __future__ import absolute_import
import contextlib
from datetime import datetime
import functools
import json
import sys
import threading
import traceback

import cinderlib
import grpc
from os_brick.initiator import connector as brick_connector
import pytz

from ember_csi import config
from ember_csi import constants


@contextlib.contextmanager
def noop_cm():
    yield


class Worker(object):
    current_workers = {}
    locks = {}

    @classmethod
    def _unique_worker(cls, func, request_field):
        @functools.wraps(func)
        def wrapper(self, request, context):
            worker_id = getattr(request, request_field)
            my_method = func.__name__
            my_thread = threading.current_thread().ident
            current = (my_method, my_thread)

            if config.ABORT_DUPLICATES:
                lock = noop_cm()
            else:
                lock = cls.locks.get(my_method)
                if not lock:
                    lock = cls.locks[my_method] = threading.Lock()

            with lock:
                method, thread = cls.current_workers.setdefault(worker_id,
                                                                current)

                if (method, thread) != current:
                    context.abort(
                        grpc.StatusCode.ABORTED,
                        'Cannot %s on %s while thread %s is doing %s' %
                        (my_method, worker_id, thread, method))

                try:
                    return func(self, request, context)
                finally:
                    del cls.current_workers[worker_id]
        return wrapper

    @classmethod
    def unique(cls, *args):
        if len(args) == 1 and callable(args[0]):
            return cls._unique_worker(args[0], 'volume_id')
        else:
            return functools.partial(cls._unique_worker,
                                     request_field=args[0])


def logrpc(f):
    def tab(what):
        return '\t' + '\n\t'.join(filter(None, str(what).split('\n')))

    @functools.wraps(f)
    def dolog(self, request, context):
        req_id = id(request)
        start = datetime.utcnow()
        if request.ListFields():
            msg = ' params\n%s' % tab(request)
        else:
            msg = 'out params'
        sys.stdout.write('=> %s GRPC [%s]: %s with%s\n' %
                         (start, req_id, f.__name__, msg))
        try:
            result = f(self, request, context)
        except Exception as exc:
            end = datetime.utcnow()
            if context._state.code:
                code = str(context._state.code)[11:]
                details = context._state.details
                tback = ''
            else:
                code = 'Unexpected exception'
                details = exc.message
                tback = '\n' + tab(traceback.format_exc())
            sys.stdout.write('!! %s GRPC in %.0fs [%s]: %s on %s (%s)%s\n' %
                             (end, (end - start).total_seconds(), req_id, code,
                              f.__name__, details, tback))
            raise
        end = datetime.utcnow()
        if str(result):
            str_result = '\n%s' % tab(result)
        else:
            str_result = ' nothing'
        sys.stdout.write('<= %s GRPC in %.0fs [%s]: %s returns%s\n' %
                         (end, (end - start).total_seconds(), req_id,
                          f.__name__, str_result))
        return result
    return dolog


def no_debug(f):
    return f


def debug(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        global DEBUG_ON
        if DEBUG_ON:
            DEBUG_LIBRARY.set_trace()
        return f(*args, **kwargs)
    return wrapper


def setup_debug():
    def toggle_debug(signum, stack):
        global DEBUG_ON
        DEBUG_ON = not DEBUG_ON
        sys.stdout.write('Debugging is %s\n' % ('ON' if DEBUG_ON else 'OFF'))

    if config.DEBUG_MODE not in ('', 'PDB', 'RPDB'):
        sys.stderr.write('Invalid X_CSI_DEBUG_MODE %s (valid values are PDB '
                         'and RPDB)\n' % config.DEBUG_MODE)
        exit(3)

    if not config.DEBUG_MODE:
        return None, no_debug

    if config.DEBUG_MODE == 'PDB':
        import pdb as debug_library
    else:
        from ember_csi import rpdb as debug_library

    import signal
    signal.signal(signal.SIGUSR1, toggle_debug)

    return debug_library, debug


DEBUG_ON = False
DEBUG_LIBRARY, debuggable = setup_debug()


def date_to_nano(date):
    # Don't use str or six.text_type, as they truncate
    return repr((date - constants.EPOCH).total_seconds() *
                constants.NANOSECONDS)


def nano_to_date(nanoseconds):
    date = datetime.utcfromtimestamp(float(nanoseconds)/constants.NANOSECONDS)
    return date.replace(tzinfo=pytz.UTC)


def require(*fields):
    fields = set(fields)

    def join(what):
        return ', '.join(what)

    def func_wrapper(f):
        @functools.wraps(f)
        def checker(self, request, context):
            request_fields = {f[0].name for f in request.ListFields()}
            missing = fields - request_fields
            if missing:
                msg = 'Missing required fields: %s' % join(missing)
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)
            return f(self, request, context)
        return checker
    return func_wrapper


class NodeInfo(object):
    __slots__ = ('id', 'connector_dict')

    def __init__(self, node_id, connector_dict):
        self.id = node_id
        self.connector_dict = connector_dict

    @classmethod
    def get(cls, node_id):
        kv = cinderlib.Backend.persistence.get_key_values(node_id)
        if not kv:
            return None
        return cls(node_id, json.loads(kv[0].value))

    @classmethod
    def set(cls, node_id, storage_nw_ip):
        # For now just set multipathing and not enforcing it
        connector_dict = brick_connector.get_connector_properties(
            'sudo', storage_nw_ip, config.REQUEST_MULTIPATH, False)
        value = json.dumps(connector_dict, separators=(',', ':'))
        kv = cinderlib.KeyValue(node_id, value)
        cinderlib.Backend.persistence.set_key_value(kv)
        return NodeInfo(node_id, connector_dict)


class EnumWrapper(object):
    def __init__(self, enum):
        self._enum = enum

    def __getattr__(self, name):
        try:
            return getattr(self._enum, name)
        except AttributeError:
            return self._enum.Value(name)
