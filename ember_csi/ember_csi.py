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
import sys
import tarfile
import time

import cinderlib
import grpc

from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi import workarounds


def main():
    config.validate()
    server_class = _get_csi_server_class(class_name=config.MODE.title())
    copy_system_files()

    mode_msg = 'in ' + config.MODE + ' mode ' if config.MODE != 'all' else ''
    print('Starting Ember CSI v%s %s(cinderlib: v%s, cinder: v%s, '
          'CSI spec: v%s)' % (constants.VENDOR_VERSION,
                              mode_msg,
                              cinderlib.__version__,
                              constants.CINDER_VERSION,
                              config.CSI_SPEC))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    workarounds.grpc_eventlet(server)
    csi_plugin = server_class(server=server,
                              persistence_config=config.PERSISTENCE_CONFIG,
                              backend_config=config.BACKEND_CONFIG,
                              ember_config=config.EMBER_CONFIG,
                              storage_nw_ip=config.STORAGE_NW_IP,
                              node_id=config.NODE_ID)

    msg = 'Running as %s' % config.MODE
    if config.MODE != 'node':
        driver_name = type(csi_plugin.backend.driver).__name__
        msg += ' with backend %s v%s' % (driver_name,
                                         csi_plugin.backend.get_version())
    print(msg)

    if common.DEBUG_LIBRARY:
        debug_msg = ('ENABLED with %s and OFF. Toggle it with SIGUSR1' %
                     common.DEBUG_LIBRARY.__name__)
    else:
        debug_msg = 'DISABLED'
    print('Debugging feature is %s.' % debug_msg)
    print('Supported filesystems: %s' % ', '.join(config.SUPPORTED_FS_TYPES))

    if not server.add_insecure_port(config.ENDPOINT):
        sys.stderr.write('\nERROR: Could not bind to %s\n' % config.ENDPOINT)
        exit(1)

    server.start()
    print('Now serving on %s...' % config.ENDPOINT)

    try:
        while True:
            time.sleep(constants.ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


def _get_csi_server_class(class_name):
    module_name = 'ember_csi.v%s.csi' % config.CSI_SPEC.replace('.', '_')
    module = importlib.import_module(module_name)
    server_class = getattr(module, class_name)
    return server_class


def copy_system_files():
    # Minimal check of the archive for files/dirs only and not devices, etc
    def check_files(members):
        for tarinfo in members:
            if tarinfo.isdev():
                sys.stderr.write("Skipping %s\n" % tarinfo.name)
            else:
                sys.stdout.write("Exctracting %s\n" % tarinfo.name)
                yield tarinfo

    archive = config.SYSTEM_FILES
    if archive:
        try:
            with tarfile.open(archive, 'r') as t:
                t.extractall('/', members=check_files(t))
        except Exception as exc:
            sys.stderr.write('Error expanding file %s %s\n' % (archive, exc))
            exit(4)
    else:
        sys.stdout.write('X_CSI_SYSTEM_FILES not specified.\n')


if __name__ == '__main__':
    main()
