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
import collections
from distutils import version
import glob
import json
import os
import re
import socket
import sys

from ember_csi import constants
from ember_csi import defaults


def _load_json_config(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default

    try:
        return json.loads(value)
    except Exception:
        print('Invalid JSON data for %s' % name)
        exit(constants.ERROR_JSON)


def _get_system_fs_types():
    fs_types = glob.glob(defaults.MKFS + '*')
    start = len(defaults.MKFS)
    result = [fst[start:] for fst in fs_types]
    return result


CSI_SPEC = os.environ.get('X_CSI_SPEC_VERSION', defaults.SPEC_VERSION)
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
PLUGIN_NAME = EMBER_CONFIG.pop('plugin_name', None) or defaults.NAME
BACKEND_CONFIG = _load_json_config('X_CSI_BACKEND_CONFIG')
NODE_ID = os.environ.get('X_CSI_NODE_ID') or socket.getfqdn()
DEFAULT_MOUNT_FS = os.environ.get('X_CSI_DEFAULT_MOUNT_FS', defaults.MOUNT_FS)
NODE_TOPOLOGY = os.environ.get('X_CSI_NODE_TOPOLOGY')
TOPOLOGIES = os.environ.get('X_CSI_TOPOLOGIES')

SUPPORTED_FS_TYPES = _get_system_fs_types()


def validate():
    global CSI_SPEC

    if MODE not in ('controller', 'node', 'all'):
        sys.stderr.write('Invalid mode value (%s)\n' % MODE)
        exit(constants.ERROR_MODE)

    if MODE != 'node' and not BACKEND_CONFIG:
        print('Missing required backend configuration')
        exit(constants.ERROR_MISSING_BACKEND)

    if not re.match(r'^[A-Za-z]{2,6}(\.[A-Za-z0-9-]{1,63})+$', PLUGIN_NAME):
        sys.stderr.write('Invalid plugin name %s' % PLUGIN_NAME)
        exit(constants.ERROR_PLUGIN_NAME)

    if DEFAULT_MOUNT_FS not in SUPPORTED_FS_TYPES:
        sys.stderr.write('Invalid default mount filesystem %s\n' %
                         DEFAULT_MOUNT_FS)
        exit(constants.ERROR_FS_TYPE)

    # Accept spaces and a v prefix on CSI spec version
    spec_version = CSI_SPEC.strip()
    if spec_version.startswith('v'):
        spec_version = spec_version[1:]

    # Support both x, x.y, and x.y.z versioning, but convert it to x.y.z
    if '.' not in spec_version:
        spec_version += '.0'
    spec_version = version.StrictVersion(spec_version)
    spec_version = '%s.%s.%s' % spec_version.version

    if spec_version not in constants.SUPPORTED_SPEC_VERSIONS:
        sys.stderr.write('CSI spec %s not in supported versions: %s.\n' %
                         (CSI_SPEC,
                          ', '.join(constants.SUPPORTED_SPEC_VERSIONS)))
        exit(constants.ERROR_CSI_SPEC)

    # Store version in x.y.z formatted string
    CSI_SPEC = spec_version

    _set_topology_config()


def _set_topology_config():
    global NODE_TOPOLOGY
    global TOPOLOGIES

    if not (TOPOLOGIES or NODE_TOPOLOGY):
        return

    if CSI_SPEC == '0.2.0':
        sys.stderr.write('Topology not supported on spec v0.2.0')
        exit(constants.ERROR_TOPOLOGY_UNSUPPORTED)

    # Decode topology using ordered dicts to determine the hierarchy
    decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
    if TOPOLOGIES:
        try:
            TOPOLOGIES = decoder.decode(TOPOLOGIES)
        except Exception:
            sys.stderr.write('Topology information is not valid JSON: %s.\n' %
                             TOPOLOGIES)
            exit(constants.ERROR_TOPOLOGY_JSON)
        if not isinstance(TOPOLOGIES, list):
            sys.stderr.write('Topologies must be a list.\n')
            exit(constants.ERROR_TOPOLOGY_LIST)

    if NODE_TOPOLOGY:
        try:
            NODE_TOPOLOGY = decoder.decode(NODE_TOPOLOGY)
        except Exception:
            sys.stderr.write(
                'Node Topology information is not valid JSON: %s.\n' %
                NODE_TOPOLOGY)
            exit(constants.ERROR_TOPOLOGY_JSON)

    if MODE == 'node':
        if TOPOLOGIES:
            sys.stderr.write('Warning: Ignoring Controller topology\n')
            if not NODE_TOPOLOGY:
                sys.stderr.write('Missing node topology\n')
                exit(constants.ERROR_TOPOLOGY_MISSING)

    elif MODE == 'controller':
        if NODE_TOPOLOGY:
            sys.stderr.write('Warning: Ignoring Node topology\n')
            if not TOPOLOGIES:
                sys.stderr.write('Missing controller topologies\n')
                exit(constants.ERROR_TOPOLOGY_MISSING)

    else:
        if not TOPOLOGIES:
            sys.stderr.write('Warning: Setting topologies to node topology\n')
            TOPOLOGIES = [NODE_TOPOLOGY]
        elif not NODE_TOPOLOGY:
            sys.stderr.write('Warning: Setting node topology to first '
                             'controller topology\n')
            NODE_TOPOLOGY = TOPOLOGIES[0]
