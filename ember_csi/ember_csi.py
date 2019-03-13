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


def main():
    CONF.validate()
    server_class = _get_csi_server_class(class_name=CONF.MODE.title())

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=CONF.WORKERS))
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

    try:
        while True:
            time.sleep(constants.ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


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
