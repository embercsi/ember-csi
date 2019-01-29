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
import errno
import glob
import json
import os
import re
import socket

import cinderlib
from oslo_context import context as context_utils
from oslo_log import log as logging
import six

from ember_csi import constants
from ember_csi import defaults


LOG = logging.getLogger(__name__)


def _load_json_config(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default

    try:
        return json.loads(value)
    except Exception:
        LOG.exception('Invalid JSON data for %s' % name)
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
# REQUEST_MULTIPATH, WORKERS, PLUGIN_NAME, ENABLE_PROBE are set from
# EMBER_CONFIG on _set_defaults_ember_cfg
BACKEND_CONFIG = _load_json_config('X_CSI_BACKEND_CONFIG')
NODE_ID = os.environ.get('X_CSI_NODE_ID') or socket.getfqdn()
DEFAULT_MOUNT_FS = os.environ.get('X_CSI_DEFAULT_MOUNT_FS', defaults.MOUNT_FS)
NODE_TOPOLOGY = os.environ.get('X_CSI_NODE_TOPOLOGY')
TOPOLOGIES = os.environ.get('X_CSI_TOPOLOGIES')

SUPPORTED_FS_TYPES = _get_system_fs_types()


def validate():
    global CSI_SPEC
    global WORKERS

    _set_logging_config()
    if MODE not in ('controller', 'node', 'all'):
        LOG.error('Invalid mode value (%s)' % MODE)
        exit(constants.ERROR_MODE)

    if MODE != 'node' and not BACKEND_CONFIG:
        LOG.error('Missing required backend configuration')
        exit(constants.ERROR_MISSING_BACKEND)

    if not re.match(r'^[A-Za-z]{2,6}(\.[A-Za-z0-9-]{1,63})+$', PLUGIN_NAME):
        LOG.error('Invalid plugin name %s' % PLUGIN_NAME)
        exit(constants.ERROR_PLUGIN_NAME)

    if DEFAULT_MOUNT_FS not in SUPPORTED_FS_TYPES:
        LOG.error('Invalid default mount filesystem %s' % DEFAULT_MOUNT_FS)
        exit(constants.ERROR_FS_TYPE)

    if not isinstance(WORKERS, int) or not WORKERS:
        LOG.error('grpc_workers must be a positive integer number')
        exit(constants.ERROR_WORKERS)

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
        LOG.error('CSI spec %s not in supported versions: %s' %
                  (CSI_SPEC, ', '.join(constants.SUPPORTED_SPEC_VERSIONS)))
        exit(constants.ERROR_CSI_SPEC)

    # Store version in x.y.z formatted string
    CSI_SPEC = spec_version

    _set_defaults_ember_cfg()
    _map_backend_config()
    _set_topology_config()
    _create_default_dirs_files()


def _get_drivers_map():
    def get_key(driver_name):
        key = driver_name.lower()
        if key.endswith('driver'):
            key = key[:-6]
        return key

    try:
        drivers = cinderlib.list_supported_drivers()
    except Exception:
        LOG.warning('System driver mappings not loaded')
        return {}

    mapping = {get_key(k): v['class_fqn'] for k, v in drivers.items()}
    return mapping


def _map_backend_config():
    """Transform key and values to make config easier for users."""
    if not BACKEND_CONFIG:
        return

    # Have simpler names for some configuration options
    for key, replacement in constants.BACKEND_KEY_MAPPINGS:
        if key in BACKEND_CONFIG:
            BACKEND_CONFIG.setdefault(replacement, BACKEND_CONFIG.pop(key))

    # Have simpler name drivers
    mapping = _get_drivers_map()
    replacement = mapping.get(BACKEND_CONFIG.get('volume_driver').lower())
    if replacement:
        BACKEND_CONFIG['volume_driver'] = replacement


def _set_defaults_ember_cfg():
    global REQUEST_MULTIPATH
    global WORKERS
    global PLUGIN_NAME
    global ENABLE_PROBE

    # First set defaults for missing keys
    for key, value in defaults.EMBER_CFG.items():
        EMBER_CONFIG.setdefault(key, value)

    # Now convert $state_path
    state_path = EMBER_CONFIG['state_path']
    for key, value in EMBER_CONFIG.items():
        if isinstance(value, six.string_types) and '$state_path' in value:
            EMBER_CONFIG[key] = value.replace('$state_path', state_path)
    defaults.VOL_BINDS_DIR = defaults.VOL_BINDS_DIR.replace('$state_path',
                                                            state_path)

    # Now set global variables
    REQUEST_MULTIPATH = EMBER_CONFIG.pop('request_multipath')
    WORKERS = EMBER_CONFIG.pop('grpc_workers')
    PLUGIN_NAME = EMBER_CONFIG.pop('plugin_name')
    ENABLE_PROBE = EMBER_CONFIG.pop('enable_probe')


def _create_default_dirs_files():
    def create_dir(name):
        try:
            os.makedirs(name)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def create_file(name):
        with open(name, 'a'):
            pass

    create_dir(EMBER_CONFIG['state_path'])
    create_dir(defaults.VOL_BINDS_DIR)
    create_dir(EMBER_CONFIG['file_locks_path'])

    default_hosts = os.path.join(EMBER_CONFIG['state_path'],
                                 'ssh_known_hosts')
    hosts_file = EMBER_CONFIG.get('ssh_hosts_key_file', default_hosts)
    create_file(hosts_file)


def _set_logging_config():
    context_utils.generate_request_id = lambda: '-'
    context_utils.get_current().request_id = '-'

    EMBER_CONFIG.setdefault(
        'logging_context_format_string',
        '%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s')
    EMBER_CONFIG.setdefault('disable_logs', False)

    if EMBER_CONFIG.get('debug'):
        log_levels = defaults.DEBUG_LOG_LEVELS
    else:
        log_levels = defaults.LOG_LEVELS
    EMBER_CONFIG.setdefault('default_log_levels', log_levels)


def _set_topology_config():
    global NODE_TOPOLOGY
    global TOPOLOGIES

    if not (TOPOLOGIES or NODE_TOPOLOGY):
        return

    if CSI_SPEC == '0.2.0':
        LOG.error('Topology not supported on spec v0.2.0')
        exit(constants.ERROR_TOPOLOGY_UNSUPPORTED)

    # Decode topology using ordered dicts to determine the hierarchy
    decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
    if TOPOLOGIES:
        try:
            TOPOLOGIES = decoder.decode(TOPOLOGIES)
        except Exception:
            LOG.error('Topology information is not valid JSON: %s' %
                      TOPOLOGIES)
            exit(constants.ERROR_TOPOLOGY_JSON)
        if not isinstance(TOPOLOGIES, list):
            LOG.error('Topologies must be a list.')
            exit(constants.ERROR_TOPOLOGY_LIST)

    if NODE_TOPOLOGY:
        try:
            NODE_TOPOLOGY = decoder.decode(NODE_TOPOLOGY)
        except Exception:
            LOG.error('Node Topology information is not valid JSON: %s' %
                      NODE_TOPOLOGY)
            exit(constants.ERROR_TOPOLOGY_JSON)

    if MODE == 'node':
        if TOPOLOGIES:
            LOG.warn('Ignoring Controller topology')
            if not NODE_TOPOLOGY:
                LOG.error('Missing node topology\n')
                exit(constants.ERROR_TOPOLOGY_MISSING)

    elif MODE == 'controller':
        if NODE_TOPOLOGY:
            LOG.warn('Ignoring Node topology')
            if not TOPOLOGIES:
                LOG.error('Missing controller topologies')
                exit(constants.ERROR_TOPOLOGY_MISSING)

    else:
        if not TOPOLOGIES:
            LOG.warn('Setting topologies to node topology')
            TOPOLOGIES = [NODE_TOPOLOGY]
        elif not NODE_TOPOLOGY:
            LOG.warn('Setting node topology to first controller topology')
            NODE_TOPOLOGY = TOPOLOGIES[0]
