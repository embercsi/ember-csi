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
import glob
import json
import os
import socket
import sys

from ember_csi import defaults


def _load_json_config(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default

    try:
        return json.loads(value)
    except Exception:
        print('Invalid JSON data for %s' % name)
        exit(1)


def _get_system_fs_types():
    fs_types = glob.glob(defaults.MKFS + '*')
    start = len(defaults.MKFS)
    result = [fst[start:] for fst in fs_types]
    return result


ABORT_DUPLICATES = (
    (os.environ.get('X_CSI_ABORT_DUPLICATES') or '').upper() == 'TRUE')
DEBUG_MODE = str(os.environ.get('X_CSI_DEBUG_MODE') or '').upper()
SYSTEM_FILES = os.environ.get('X_CSI_SYSTEM_FILES')
# CSI_ENDPOINT should accept multiple formats 0.0.0.0:5000, unix:foo.sock
ENDPOINT = os.environ.get('CSI_ENDPOINT', defaults.ENDPOINT)
MODE = (os.environ.get('CSI_MODE') or defaults.MODE).lower()
STORAGE_NW_IP = (os.environ.get('X_CSI_STORAGE_NW_IP') or
                 socket.gethostbyname(socket.gethostname()))
PERSISTENCE_CONFIG = (_load_json_config('X_CSI_PERSISTENCE_CONFIG') or
                      defaults.PERSISTENCE_CFG)
EMBER_CONFIG = _load_json_config('X_CSI_EMBER_CONFIG',
                                 defaults.EMBER_CFG)
REQUEST_MULTIPATH = EMBER_CONFIG.pop('request_multipath',
                                     defaults.REQUEST_MULTIPATH)
BACKEND_CONFIG = _load_json_config('X_CSI_BACKEND_CONFIG')
NODE_ID = os.environ.get('X_CSI_NODE_ID')
DEFAULT_MOUNT_FS = os.environ.get('X_CSI_DEFAULT_MOUNT_FS', defaults.MOUNT_FS)

SUPPORTED_FS_TYPES = _get_system_fs_types()


def validate():
    if MODE not in ('controller', 'node', 'all'):
        sys.stderr.write('Invalid mode value (%s)\n' % MODE)
        exit(1)

    if MODE != 'node' and not BACKEND_CONFIG:
        print('Missing required backend configuration')
        exit(2)

    if DEFAULT_MOUNT_FS not in SUPPORTED_FS_TYPES:
        sys.stderr.write('Invalid default mount filesystem %s\n' %
                         DEFAULT_MOUNT_FS)
        exit(1)
