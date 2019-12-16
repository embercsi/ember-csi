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
import tarfile

import cinderlib
from oslo_context import context as context_utils
from oslo_log import log as logging
import six

from ember_csi import constants
from ember_csi import defaults


LOG = logging.getLogger(__name__)


class Config(object):
    @staticmethod
    def _env_string(name, default=''):
        return os.environ.get(name, default) or default

    @staticmethod
    def _env_bool(name, default=False):
        res = os.environ.get('X_CSI_ABORT_DUPLICATES')
        if not res:
            res = str(default)
        return res.upper() == 'TRUE'

    @staticmethod
    def _env_json(name, default=None):
        value = os.environ.get(name)
        if not value:
            return default

        try:
            return json.loads(value)
        except Exception:
            LOG.exception('Invalid JSON data for %s' % name)
            exit(constants.ERROR_JSON)

    @staticmethod
    def _get_system_fs_types():
        fs_types = glob.glob(defaults.MKFS + '*')
        start = len(defaults.MKFS)
        result = [fst[start:] for fst in fs_types]
        return result

    @classmethod
    def _get_ember_cfg(cls):
        config = cls._env_json('X_CSI_EMBER_CONFIG', defaults.EMBER_CFG)

        # First set defaults for missing keys
        for key, value in defaults.EMBER_CFG.items():
            config.setdefault(key, value)

        # Now convert $state_path
        state_path = config['state_path']
        for key, value in config.items():
            if isinstance(value, six.string_types) and '$state_path' in value:
                config[key] = value.replace('$state_path', state_path)
        defaults.VOL_BINDS_DIR = defaults.VOL_BINDS_DIR.replace('$state_path',
                                                                state_path)
        return config

    def _set_logging(self, config):
        context_utils.RequestContext(
            overwrite=True,
            user_id=self.EMBER_CONFIG['user_id'],
            project_id=self.EMBER_CONFIG['project_id'],
            request_id='-')

        config.setdefault('logging_context_format_string',
                          defaults.LOGGING_FORMAT)
        config.setdefault('disable_logs', False)

        if config.get('debug'):
            log_levels = defaults.DEBUG_LOG_LEVELS
        else:
            log_levels = defaults.LOG_LEVELS
        config.setdefault('default_log_levels', log_levels)

    def __init__(self):
        self.CSI_SPEC = self._env_string('X_CSI_SPEC_VERSION',
                                         defaults.SPEC_VERSION)
        self.ABORT_DUPLICATES = self._env_bool('X_CSI_ABORT_DUPLICATES')
        self.DEBUG_MODE = self._env_string('X_CSI_DEBUG_MODE').upper()
        self.SYSTEM_FILES = self._env_string('X_CSI_SYSTEM_FILES')

        # CSI_ENDPOINT accepts multiple formats 0.0.0.0:5000, unix:foo.sock
        self.ENDPOINT = self._env_string('CSI_ENDPOINT', defaults.ENDPOINT)
        self.MODE = self._env_string('CSI_MODE', defaults.MODE).lower()

        my_ip = socket.gethostbyname(socket.gethostname())
        self.STORAGE_NW_IP = self._env_string('X_CSI_STORAGE_NW_IP', my_ip)
        self.PERSISTENCE_CONFIG = self._env_json('X_CSI_PERSISTENCE_CONFIG',
                                                 defaults.PERSISTENCE_CFG)
        self.BACKEND_CONFIG = self._env_json('X_CSI_BACKEND_CONFIG')
        self.NODE_ID = self._env_string('X_CSI_NODE_ID', socket.getfqdn())
        self.DEFAULT_MOUNT_FS = self._env_string('X_CSI_DEFAULT_MOUNT_FS',
                                                 defaults.MOUNT_FS)
        self.NODE_TOPOLOGY = self._env_string('X_CSI_NODE_TOPOLOGY')
        self.TOPOLOGIES = self._env_string('X_CSI_TOPOLOGIES')
        self.SUPPORTED_FS_TYPES = self._get_system_fs_types()

        EMBER_CONFIG = self._get_ember_cfg()

        # Now set global variables that come from ember_config
        self.REQUEST_MULTIPATH = EMBER_CONFIG.pop('request_multipath',
                                                  defaults.REQUEST_MULTIPATH)
        self.WORKERS = EMBER_CONFIG.pop('grpc_workers', defaults.WORKERS)

        self.PLUGIN_NAME = EMBER_CONFIG.pop('plugin_name')
        self.ENABLE_PROBE = EMBER_CONFIG.pop('enable_probe',
                                             defaults.ENABLE_PROBE)
        self.HAS_SLOW_OPERATIONS = EMBER_CONFIG.pop('slow_operations')
        self.EMBER_CONFIG = EMBER_CONFIG

        self._set_logging(self.EMBER_CONFIG)

    @staticmethod
    def _get_names(csi_version, plugin_name):
        # In spec < 1.0 name must follow reverse domain name notation
        reverse = version.StrictVersion(csi_version) < '1.0'
        if reverse:
            data = [defaults.REVERSE_NAME, plugin_name]
            regex = r'^[A-Za-z]{2,6}(\.[A-Za-z0-9-]{1,63})+$'
        # In spec 1.0 the name must be domain name notation
        else:
            data = [plugin_name, defaults.NAME]
            regex = r'^([A-Za-z0-9-]{1,63}\.)+?[A-Za-z]{2,6}$'

        # For backward compatibility, accept full name
        if 'ember-csi' in plugin_name:
            name = plugin_name
        else:
            name = '.'.join(filter(None, data))

        if len(name) > 63:
            LOG.error('Plugin name %s too long (max %s)' %
                      (plugin_name, 63 - len(defaults.NAME)))
            exit(constants.ERROR_PLUGIN_NAME)

        if not re.match(regex, name):
            LOG.error('Invalid plugin name %s' % plugin_name)
            exit(constants.ERROR_PLUGIN_NAME)

        if not plugin_name:
            project_name = 'default'
        else:
            project_name = name.split('.')[-1 if reverse else 0]
        return name, project_name

    def validate(self):
        self._untar_file(self.SYSTEM_FILES)

        if self.MODE not in ('controller', 'node', 'all'):
            LOG.error('Invalid mode value (%s)' % self.MODE)
            exit(constants.ERROR_MODE)

        if self.MODE != 'node' and not self.BACKEND_CONFIG:
            LOG.error('Missing required backend configuration')
            exit(constants.ERROR_MISSING_BACKEND)

        if self.DEFAULT_MOUNT_FS not in self.SUPPORTED_FS_TYPES:
            LOG.error('Invalid default mount filesystem %s' %
                      self.DEFAULT_MOUNT_FS)
            exit(constants.ERROR_FS_TYPE)

        if not isinstance(self.WORKERS, int) or not self.WORKERS:
            LOG.error('grpc_workers must be a positive integer number')
            exit(constants.ERROR_WORKERS)

        # Accept spaces and a v prefix on CSI spec version
        spec_version = self.CSI_SPEC.strip()
        if spec_version.startswith('v'):
            spec_version = spec_version[1:]

        # Support both x, x.y, and x.y.z versioning, but convert it to x.y.z
        if '.' not in spec_version:
            spec_version += '.0'
        spec_version = version.StrictVersion(spec_version)
        spec_version = '%s.%s.%s' % spec_version.version

        if spec_version not in constants.SUPPORTED_SPEC_VERSIONS:
            LOG.error('CSI spec %s not in supported versions: %s' %
                      (self.CSI_SPEC,
                       ', '.join(constants.SUPPORTED_SPEC_VERSIONS)))
            exit(constants.ERROR_CSI_SPEC)

        # Store version in x.y.z formatted string
        self.CSI_SPEC = spec_version
        self.NAME, self.PROJECT_NAME = self._get_names(spec_version,
                                                       self.PLUGIN_NAME)
        context_utils.get_current().project_name = self.PROJECT_NAME

        self._map_backend_config(self.BACKEND_CONFIG)
        self._set_topology_config()
        self._create_default_dirs_files()

    @staticmethod
    def _get_drivers_map():
        """Get mapping for drivers NiceName to PythonNamespace."""
        def get_key(driver_name):
            """Return driver nice name.

            Driver nice name comes from lowercased class name without the
            driver sufix.
            """
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

    def _map_backend_config(self, backend_config):
        """Transform key and values to make config easier for users."""
        if not backend_config:
            return

        # Have simpler names for some configuration options
        for key, replacement in constants.BACKEND_KEY_MAPPINGS:
            if key in backend_config:
                backend_config.setdefault(replacement, backend_config.pop(key))

        # Replace simpler driver names with full Python Namespace
        mapping = self._get_drivers_map()
        replacement = mapping.get(backend_config.get('volume_driver').lower())
        if replacement:
            backend_config['volume_driver'] = replacement

    def _create_default_dirs_files(self):
        def create_dir(name):
            try:
                os.makedirs(name)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

        def create_file(name):
            with open(name, 'a'):
                pass

        create_dir(self.EMBER_CONFIG['state_path'])
        create_dir(defaults.VOL_BINDS_DIR)
        create_dir(self.EMBER_CONFIG['file_locks_path'])

        default_hosts = os.path.join(self.EMBER_CONFIG['state_path'],
                                     'ssh_known_hosts')
        hosts_file = self.EMBER_CONFIG.get('ssh_hosts_key_file', default_hosts)
        create_file(hosts_file)

    def _set_topology_config(self):
        if not (self.TOPOLOGIES or self.NODE_TOPOLOGY):
            return

        if self.CSI_SPEC == '0.2.0':
            LOG.error('Topology not supported on spec v0.2.0')
            exit(constants.ERROR_TOPOLOGY_UNSUPPORTED)

        # Decode topology using ordered dicts to determine the hierarchy
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        if self.TOPOLOGIES:
            try:
                self.TOPOLOGIES = decoder.decode(self.TOPOLOGIES)
            except Exception:
                LOG.error('Topology information is not valid JSON: %s' %
                          self.TOPOLOGIES)
                exit(constants.ERROR_TOPOLOGY_JSON)
            if not isinstance(self.TOPOLOGIES, list):
                LOG.error('Topologies must be a list.')
                exit(constants.ERROR_TOPOLOGY_LIST)

        if self.NODE_TOPOLOGY:
            try:
                self.NODE_TOPOLOGY = decoder.decode(self.NODE_TOPOLOGY)
            except Exception:
                LOG.error('Node Topology information is not valid JSON: %s' %
                          self.NODE_TOPOLOGY)
                exit(constants.ERROR_TOPOLOGY_JSON)

        if self.MODE == 'node':
            if self.TOPOLOGIES:
                LOG.warn('Ignoring Controller topology')
                if not self.NODE_TOPOLOGY:
                    LOG.error('Missing node topology\n')
                    exit(constants.ERROR_TOPOLOGY_MISSING)

        elif self.MODE == 'controller':
            if self.NODE_TOPOLOGY:
                LOG.warn('Ignoring Node topology')
                if not self.TOPOLOGIES:
                    LOG.error('Missing controller topologies')
                    exit(constants.ERROR_TOPOLOGY_MISSING)

        else:
            if not self.TOPOLOGIES:
                LOG.warn('Setting topologies to node topology')
                self.TOPOLOGIES = [self.NODE_TOPOLOGY]
            elif not self.NODE_TOPOLOGY:
                LOG.warn('Setting node topology to first controller topology')
                self.NODE_TOPOLOGY = self.TOPOLOGIES[0]

    @staticmethod
    def _untar_file(archive):
        # Minimal check of the archive for files/dirs only and not devices, etc
        def check_files(members):
            for tarinfo in members:
                if tarinfo.isdev():
                    LOG.debug("Skipping %s" % tarinfo.name)
                else:
                    LOG.info("Extracting %s\n" % tarinfo.name)
                    yield tarinfo

        if archive:
            try:
                with tarfile.open(archive, 'r') as t:
                    t.extractall('/', members=check_files(t))
            except Exception as exc:
                LOG.error('Error expanding file %s %s' % (archive, exc))
                exit(constants.ERROR_TAR)
        else:
            LOG.debug('X_CSI_SYSTEM_FILES not specified.\n')


CONF = Config()
