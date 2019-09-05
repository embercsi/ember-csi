#!/usr/bin/env python
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

# TODO(geguileo): Check that all parameters are present on received RPC calls
from __future__ import absolute_import
from concurrent import futures
import importlib
import os
import signal
import threading
import time

import eventlet
eventlet.monkey_patch()  # noqa

import grpc
from oslo_log import log as logging

from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi import workarounds


CONF = config.CONF
LOG = logging.getLogger(__name__)
SHUTDOWN_EVENT = threading.Event()
# Give priority to graceful stop (30 minutes timeout) over quick stop, and let
# the operator kill us sooner if necessary.
GRACEFUL_TIMEOUT = 30


def main():
    CONF.validate()
    server_class = _get_csi_server_class(class_name=CONF.MODE.title())

    if CONF.HAS_SLOW_OPERATIONS:
        options = (
            # allow keepalive pings when there's no gRPC calls
            ('grpc.keepalive_permit_without_calls', True),
            # allow unlimited amount of keepalive pings without data
            ('grpc.http2.max_pings_without_data', 0),
            # allow grpc pings from client every 1 seconds
            ('grpc.http2.min_time_between_pings_ms', 1000),
            # allow grpc pings from client without data every 1 seconds
            ('grpc.http2.min_ping_interval_without_data_ms',  1000),
            # Support unlimited misbehaving pings
            ('grpc.http2.max_ping_strikes', 0),
        )
    else:
        options = None

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=CONF.WORKERS),
                         options=options)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    workarounds.grpc_eventlet(server)
    node_id = CONF.NAME + '.' + CONF.NODE_ID
    csi_plugin = server_class(server=server,
                              persistence_config=CONF.PERSISTENCE_CONFIG,
                              backend_config=CONF.BACKEND_CONFIG,
                              ember_config=CONF.EMBER_CONFIG,
                              storage_nw_ip=CONF.STORAGE_NW_IP,
                              node_id=node_id)

    _log_used_parameters(csi_plugin)

    if not server.add_insecure_port(CONF.ENDPOINT):
        LOG.error('ERROR: Could not bind to %s' % CONF.ENDPOINT)
        exit(constants.ERROR_BIND_PORT)

    server.start()
    LOG.info('Now serving on %s...' % CONF.ENDPOINT)

    # Wait until we receive a signal to stop the server
    SHUTDOWN_EVENT.wait()

    stop_server(server)


def shutdown_handler(signum, stack):
    # NOTE: We cannot stop everything here because if we call server.stop we
    # get error: "AssertionError: Cannot switch to MAINLOOP from MAINLOOP", so
    # we let the main loop stop the server
    signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
    LOG.info('Received signal %s' % signal_name)
    SHUTDOWN_EVENT.set()


def stop_server(server):
    def force_stop():
        time.sleep(2)
        LOG.error('Failed to stop process, killing ourselves')
        os.kill(os.getpid(), signal.SIGKILL)

    LOG.info('Gracefully stopping server')
    shutdown_hadler = server.stop(60 * GRACEFUL_TIMEOUT)
    shutdown_hadler.wait()

    # There is threading issue and the process doesn't actually stop until all
    # the threads have completed.  So we start a thread that forcefully kills
    # us in 2 seconds if that's the case.
    threading.Thread(target=force_stop).start()


def _get_csi_server_class(class_name):
    module_name = 'ember_csi.v%s.csi' % CONF.CSI_SPEC.replace('.', '_')
    module = importlib.import_module(module_name)
    server_class = getattr(module, class_name)
    return server_class


def _log_used_parameters(csi_plugin):
    LOG.info('Ember CSI v%s with %d workers (CSI spec: v%s, cinderlib: v%s, '
             'cinder: v%s)' %
             (constants.VENDOR_VERSION, CONF.WORKERS, CONF.CSI_SPEC,
              constants.CINDERLIB_VERSION, constants.CINDER_VERSION))

    LOG.info('Persistence module: %s' % type(csi_plugin.persistence).__name__)
    msg = 'Running as %s' % CONF.MODE
    if CONF.MODE != 'node':
        driver_name = type(csi_plugin.backend.driver).__name__
        msg += ' with backend %s v%s' % (driver_name,
                                         csi_plugin.backend.get_version())
    LOG.info(msg)
    LOG.info('Plugin name: %s' % CONF.NAME)

    if common.DEBUG_LIBRARY:
        debug_msg = ('ENABLED with %s and OFF. Toggle it with SIGUSR1' %
                     common.DEBUG_LIBRARY.__name__)
    else:
        debug_msg = 'DISABLED'
    LOG.info('Debugging feature is %s.' % debug_msg)
    LOG.info('Supported filesystems: %s' % (
        ', '.join(CONF.SUPPORTED_FS_TYPES)))
    if getattr(csi_plugin, 'TOPOLOGY_HIERA', None):
        LOG.debug('Topologies: %s.' % csi_plugin.TOPOLOGY_HIERA)


if __name__ == '__main__':
    main()
