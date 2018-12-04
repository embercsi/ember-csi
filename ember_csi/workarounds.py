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
from distutils import version
import functools

import eventlet
from eventlet import tpool
import kubernetes as k8s


class ServerProxy(tpool.Proxy):
    @staticmethod
    def _my_doit(method, *args, **kwargs):
        # cygrpc.Server methods don't acept proxied completion_queue
        unproxied_args = [arg._obj if isinstance(arg, tpool.Proxy) else arg
                          for arg in args]
        unproxied_kwargs = {k: v._obj if isinstance(v, tpool.Proxy) else v
                            for k, v in kwargs.items()}
        return method(*unproxied_args, **unproxied_kwargs)

    def __getattr__(self, attr_name):
        f = super(ServerProxy, self).__getattr__(attr_name)
        if hasattr(f, '__call__'):
            f = functools.partial(self._my_doit, f)
        return f

    def __call__(self, *args, **kwargs):
        return self._my_doit(super(ServerProxy, self).__call__,
                             *args, **kwargs)


def grpc_eventlet(server):
    """gRPC and eventlet workaround.

    gRPC library is not compatible with eventlet, so we have to hack our way
    around it proxying objects to run methods on native threads.
    """
    state = server._state
    state.server = ServerProxy(state.server)
    state.completion_queue = tpool.Proxy(state.completion_queue)


def eventlet_issue_147_172():
    """Workaround for evenlet issues 147 and 172

    Issues:
    - https://github.com/eventlet/eventlet/issues/147
    - https://github.com/eventlet/eventlet/issues/172

    Monkey patch eventlet's current_thread method on versions older than 0.23.0
    where this was fixed with
    https://github.com/eventlet/eventlet/commit/1d6d8924a9da6a0cb839b81e785f99b6ac219a0e
    """

    # This method is extracted from eventlet and reformatted to follow PEP8
    def current_thread():
        g = g_threading.greenlet.getcurrent()
        if not g:
            # Not currently in a greenthread, fall back to standard function
            native_thread = g_threading.__orig_threading.current_thread()
            return g_threading._fixup_thread(native_thread)

        try:
            active = g_threading.__threadlocal.active
        except AttributeError:
            active = g_threading.__threadlocal.active = {}

        g_id = id(g)
        t = active.get(g_id)
        if t is not None:
            return t

        # FIXME: move import from function body to top
        # (jaketesler@github) Furthermore, I was unable to have the
        # current_thread() return correct results from threading.enumerate()
        # unless the enumerate() function was a) imported at runtime using the
        # gross __import__() call and b) was hot-patched using
        # patch_function().
        # https://github.com/eventlet/eventlet/issues/172#issuecomment-379421165
        found = [th for th in __patched_enumerate() if th.ident == g_id]
        if found:
            return found[0]

        # Add green thread to active if we can clean it up on exit
        def cleanup(g):
            del active[g_id]
        try:
            g.link(cleanup)
        except AttributeError:
            # Not a GreenThread type, so there's no way to hook into
            # the green thread exiting. Fall back to the standard
            # function then.
            t = g_threading._fixup_thread(
                g_threading.__orig_threading.current_thread())
        else:
            t = active[g_id] = g_threading._GreenThread(g)

        return t

    if eventlet.__version__ < version.LooseVersion('0.23.0'):
        # We ensure threading is monkey patched
        if not eventlet.patcher.is_monkey_patched('thread'):
            eventlet.patcher.monkey_patch()

        import threading
        from eventlet.green import threading as g_threading

        __patched_enumerate = eventlet.patcher.patch_function(
            __import__('threading').enumerate)

        # Change Eventlet replacements with our own
        setattr(threading, 'current_thread', current_thread)
        setattr(threading, 'currentThread', current_thread)


def k8s_issue_376():
    """Workaround for https://github.com/kubernetes-client/python/issues/376

    That issue will raise a ValueError when creating a CRD because the status
    returned by Kubernetes is set to None, which according to
    V1beta1CustomResourceDefinitionStatus cannot be.

        u'status': {u'acceptedNames': {u'kind': u'', u'plural': u''},
                    u'conditions': None}}

    We replace the conditions setter to accept the None value.
    """
    def set_conditions(self, conditions):
        # Unlike the original one we accept None values
        self._conditions = conditions

    crd_status = k8s.client.models.v1beta1_custom_resource_definition_status
    crd_status_cls = crd_status.V1beta1CustomResourceDefinitionStatus
    setattr(crd_status_cls, 'conditions',
            property(fget=crd_status_cls.conditions.fget, fset=set_conditions))
