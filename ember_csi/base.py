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
import itertools
import os
import stat
import re
import socket
import sys
import time

import cinderlib
from cinderlib import exception
import grpc
from oslo_concurrency import processutils as putils
from oslo_log import log as logging
import six

from ember_csi import capabilities as capabilities_lib
from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi import defaults
from ember_csi import messages


CONF = config.CONF
LOG = logging.getLogger(__name__)

CAP_KEY = constants.CAPABILITY_KEY
CAPS_KEY = constants.CAPABILITIES_KEY

# TODO: Account for UNKNOWN access_mode


# Workaround for https://bugs.python.org/issue672115
class object(object):
    pass


class CSIMeta(type):
    """Set CSI Servicer classes as a base for our base classes."""
    @staticmethod
    def _set_base(new_base, dest_cls):
        if new_base not in dest_cls.__bases__:
            if (object,) == dest_cls.__bases__:
                dest_cls.__bases__ = (new_base,)
            else:
                dest_cls.__bases__ += (new_base,)

    def __init__(cls, name, bases, nmspc):
        if cls.CSI and not issubclass(ControllerBase,
                                      cls.CSI.ControllerServicer):
            CSIMeta._set_base(cls.CSI.ControllerServicer, ControllerBase)
            CSIMeta._set_base(cls.CSI.NodeServicer, NodeBase)
            CSIMeta._set_base(cls.CSI.IdentityServicer, IdentityBase)
        super(CSIMeta, cls).__init__(name, bases, nmspc)


class IdentityBase(object):
    __metaclass__ = CSIMeta
    # CSI and TYPES attributes must be defined on inheriting classes
    CSI = None
    TYPES = None
    backend = None
    manifest = None
    MKFS = defaults.MKFS
    DEFAULT_MKFS_ARGS = tuple()
    MKFS_ARGS = {'ext4': ('-F',)}
    PLUGIN_CAPABILITIES = []
    PLUGIN_GRPC_CAPABILITIES = []
    CONTAINERIZED = os.stat('/proc').st_dev > 4

    def __init__(self, server, ember_config):
        # Skip if we've already been initialized (happens on class All)
        if self.manifest is not None:
            return

        self.disable_features(ember_config)

        self.csi_version = version.StrictVersion(CONF.CSI_SPEC)
        self.PLUGIN_CAPABILITIES.append(
            self.TYPES.ServiceType.CONTROLLER_SERVICE)
        caps = [self.TYPES.Capability(service=self.TYPES.Service(type=t))
                for t in self.PLUGIN_CAPABILITIES]
        caps.extend(self.PLUGIN_GRPC_CAPABILITIES)
        self.PLUGIN_CAPABILITIES_RESP = self.TYPES.CapabilitiesResp(
            capabilities=caps)

        self.root_helper = ((ember_config or {}).get('root_helper') or
                            defaults.ROOT_HELPER)

        manifest = {
            'cinder-version': constants.CINDER_VERSION,
            'cinderlib-version': constants.CINDERLIB_VERSION,
        }
        self.persistence = cinderlib.Backend.persistence
        manifest['persistence'] = type(self.persistence).__name__
        manifest['mode'] = type(self).__name__.lower()
        # Only All and Controller have a configured backend
        if self.backend:
            manifest['cinder-driver-version'] = self.backend.get_version()
            manifest['cinder-driver'] = type(self.backend.driver).__name__
            manifest['cinder-driver-supported'] = str(self.backend.supported)

        self.INFO = self.TYPES.InfoResp(
            name=CONF.NAME,
            vendor_version=constants.VENDOR_VERSION,
            manifest=manifest)

        self._set_supported_modes()
        self.CSI.add_IdentityServicer_to_server(self, server)
        self.manifest = manifest
        self.PROBE_KV = cinderlib.objects.KeyValue('%s.%s.%s.%s' % (
            CONF.NAME, CONF.MODE, socket.getfqdn(), 'probe'), '0')

    def _set_supported_modes(self):
        access_modes = self.TYPES.AccessModeType
        capabilities_lib.set_access_modes(access_modes)
        self.service_capabilities = capabilities_lib.ServiceCapabilities(
            self.can_brwx, self.can_mrwx)

        # TODO: REMOVE THIS CODE
        self.SINGLE_ACCESS_MODES = (access_modes.SINGLE_NODE_WRITER,
                                    access_modes.SINGLE_NODE_READER_ONLY)
        self.MULTI_ACCESS_MODES = (access_modes.MULTI_NODE_READER_ONLY,
                                   access_modes.MULTI_NODE_SINGLE_WRITER,
                                   access_modes.MULTI_NODE_MULTI_WRITER)
        self.RO_ACCESS_MODES = (access_modes.SINGLE_NODE_READER_ONLY,
                                access_modes.MULTI_NODE_READER_ONLY)

        self.SUPPORTED_ACCESS = self.SINGLE_ACCESS_MODES
        if self.can_brwx or self.can_mrwx:
            self.SUPPORTED_ACCESS += self.MULTI_ACCESS_MODES

    @property
    def can_brwx(self):
        return constants.BLOCK_RWX_FEATURE not in self.disabled_features

    @property
    def can_mrwx(self):
        # TODO: Change when we support RWX mounts
        return False

    @classmethod
    def _get_all_classes(cls, has_method=None):
        result = set()
        bases = [cls]
        while bases:
            parent = bases.pop()
            for cls in parent.__bases__:
                if (cls not in result and
                        (not has_method or hasattr(cls, has_method))):
                    result.add(cls)
                    bases.append(cls)
        return result

    def disable_features(self, ember_config):
        bases = self._get_all_classes('_disable_features')
        self.disabled_features = ember_config['disabled']
        for cls in bases:
            cls._disable_features(self, self.disabled_features)

    def _fail_if_disabled(self, context, feature):
        if feature in self.disabled_features:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            msg = feature + ' feature is disabled!'
            context.set_details(msg)
            raise ValueError(msg)

    def _unsupported_mode(self, capability):
        mode = capability.access_mode.mode
        # Support for mount and block RWX are independent, so supported mode
        # depends on the access type
        rwx = self.can_mrwx if capability.HasField('mount') else self.can_brwx
        return (mode not in self.SUPPORTED_ACCESS
                or (mode in self.MULTI_ACCESS_MODES and not rwx))

    def _unsupported_fs_type(self, capability):
        # TODO: validate mount_flags
        return (capability.HasField('mount') and
                capability.mount.fs_type and
                capability.mount.fs_type not in CONF.SUPPORTED_FS_TYPES)

    def _validate_name(self, name):
        if name and re.match(r'^[A-Za-z]{2,6}(\.[A-Za-z0-9-]{1,63})+$', name):
            return name

        return defaults.NAME

    @common.debuggable
    @common.logrpc
    def GetPluginInfo(self, request, context):
        return self.INFO

    @common.debuggable
    @common.logrpc
    def GetPluginCapabilities(self, request, context):
        return self.PLUGIN_CAPABILITIES_RESP

    @common.debuggable
    @common.logrpc
    def Probe(self, request, context):
        # Proving may take a couple of seconds, and attacher sidecar prior to
        # v0.4 will fail due to small timeout.
        if not CONF.ENABLE_PROBE:
            return self.TYPES.ProbeRespOK

        try:
            self.PROBE_KV.value = str((int(self.PROBE_KV.value) + 1) % 1000)
            self.persistence.set_key_value(self.PROBE_KV)
            res = self.persistence.get_key_values(self.PROBE_KV.key)
            if not res or res[0].value != self.PROBE_KV.value:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                              'Storing metadata persistence value failed')
        except Exception:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Error accessing metadata persistence')

        if self.backend:
            try:
                # Check driver is OK
                self.backend.driver.check_for_setup_error()
            except Exception:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                              'Driver check setup error failed')
            try:
                # Use stats gathering to further confirm it's working fine
                self.backend.stats(refresh=True)
            except Exception:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                              'Driver failed to return the stats')

        return self.TYPES.ProbeRespOK

    def _get_vol(self, volume_id=None, always_list=False, context=None,
                 **filters):
        backend_name = self.backend.id if self.backend else None
        res = self.persistence.get_volumes(
            volume_id=volume_id, backend_name=backend_name, **filters)
        # Ignore soft-deleted volumes
        res = [vol for vol in res if vol.status != 'deleted']
        if not res and context:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % volume_id)

        if (not always_list and
                res and len(res) == 1 and (volume_id or filters)):
            return res[0]
        return res

    def sudo(self, *cmd, **kwargs):
        retries = kwargs.pop('retries', 1)
        delay = kwargs.pop('delay', 1)
        backoff = kwargs.pop('backoff', 2)
        errors = kwargs.pop('errors', [32])
        while retries:
            try:
                return putils.execute(*cmd, run_as_root=True,
                                      root_helper=self.root_helper)
            except putils.ProcessExecutionError as exc:
                retries -= 1
                if exc.exit_code not in errors or not retries:
                    raise
                time.sleep(delay)
                delay *= backoff

    def _get_size(self, what, request, default):
        vol_size = getattr(request.capacity_range, what + '_bytes', None)
        if vol_size:
            return vol_size / constants.GB
        return default

    def _calculate_size(self, request, context):
        # Must be idempotent
        min_size = self._get_size('required', request, defaults.VOLUME_SIZE)
        max_size = self._get_size('limit', request, six.MAXSIZE)
        if max_size < min_size:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Limit_bytes is smaller than required_bytes')

        if max_size < 1:
            context.abort(grpc.StatusCode.OUT_OF_RANGE,
                          'Unsupported capacity_range (min size is 1GB)')

        # Create the smallest volume that matches the request and is at least
        # 1GBi
        vol_size = max(min_size, defaults.VOLUME_SIZE)
        return (vol_size, min_size, max_size)

    @staticmethod
    def _set_metadata(vol, _save_if_changed=True, **values):
        # We do the update this way instead of just setting
        # `vol.admin_metadata['fs_type']` because then the attribute would not
        # be marked as dirty an we would have to manually call insternal method
        # `vol._ovo._changed_fields.add('admin_metadata')`
        metadata = vol._ovo.admin_metadata or {}
        original = metadata.copy()
        metadata.update(values)
        vol._ovo.admin_metadata = metadata
        if _save_if_changed and metadata != original:
            vol.save()

    @staticmethod
    def _get_fs_type(vol):
        if not vol.admin_metadata:
            return None
        return vol.admin_metadata.get('fs_type')

    @staticmethod
    def _duplicate_connection(vol, conn, capability, attach_mode, **kwargs):
        connection_info = conn.connection_info.copy()
        kwargs.setdefault('attached_host', conn.attached_host)
        new_conn = cinderlib.Connection(vol.backend,
                                        connector=conn.connector_info,
                                        volume=vol,
                                        status='attached',
                                        connection_info=connection_info,
                                        attach_mode=attach_mode,
                                        **kwargs)
        new_conn.connector_info[CAP_KEY] = capability.json
        new_conn.save()
        LOG.debug('Created connection %s duplicate of %s' %
                  (new_conn.id, conn.id))
        vol._connections.append(new_conn)
        vol._ovo.volume_attachment.objects.append(new_conn._ovo)
        return new_conn

    @staticmethod
    def _capability_to_dict(capability):
        is_block = capability.HasField('block')
        res = {'is_block': is_block,
               'access_mode': capability.access_mode.mode}
        if not is_block:
            res['fs_type'] = capability.mount.fs_type or CONF.DEFAULT_MOUNT_FS
            res['mount_flags'] = list(capability.mount.mount_flags)
        return res

    @staticmethod
    def conn_cap(conn):
        return capabilities_lib.Capability(conn.connector_info[CAP_KEY])

    def _get_conn(self, volume, capability=None, path=None, alt_path=None,
                  return_all=False, node_id=None):
        if capability and not isinstance(capability,
                                         capabilities_lib.Capability):
            capability = capabilities_lib.Capabiilty(capability)

        result = []
        alt_conn = []

        node_id = node_id or self.node_info.id
        for conn in volume.connections:
            if (node_id == conn.attached_host and
                    (capability is None or capability == self.conn_cap(conn))):

                if path is None or path == conn.mountpoint:
                    if not return_all:
                        return conn
                    result.append(conn)
                elif alt_path == conn.mountpoint:
                    alt_conn.append(conn)

        if result:
            return result

        return alt_conn if return_all else (alt_conn[0] if alt_conn else None)


class ControllerBase(IdentityBase):
    FORBIDDEN_VOL_PARAMS = ('id', 'name', 'size', 'volume_size', 'multiattach')

    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, **kwargs):
        cinderlib_extra_config = ember_config.copy()
        cinderlib_extra_config.pop('disabled')
        cinderlib.setup(persistence_config=persistence_config,
                        **cinderlib_extra_config)
        self.backend = cinderlib.Backend(**backend_config)
        IdentityBase.__init__(self, server, ember_config)
        self.CSI.add_ControllerServicer_to_server(self, server)

        self.DELETE_RESP = self.TYPES.DeleteResp()
        self.CTRL_UNPUBLISH_RESP = self.TYPES.UnpublishResp()

        capab = [self.TYPES.CtrlCapability(rpc=self.TYPES.CtrlRPC(type=rpc))
                 for rpc in self.CTRL_CAPABILITIES]
        self.CTRL_CAPABILITIES_RESP = self.TYPES.CtrlCapabilityResp(
            capabilities=capab)

        if len(self.backend.pool_names) > 1:
            LOG.info('Available pools: %s' %
                     ', '.join(self.backend.pool_names))

    def _get_vol_node(self, request, context):
        if request.node_id:
            node = common.NodeInfo.get(request.node_id)
            if not node:
                context.abort(grpc.StatusCode.NOT_FOUND,
                              'Node %s does not exist' % request.node_id)
        else:
            node = None

        vol = self._get_vol(request.volume_id, context=context)
        if vol.status not in ('in-use', 'available'):
            context.abort(grpc.StatusCode.ABORTED,
                          'Operation pending for volume %s' % vol.status)
        return (vol, node)

    def _wait(self, resource, states, delete_on_error=False):
        # TODO(geguileo): Introduce timeout and probably cleanup mechanism
        status = resource.status
        try:
            while status not in states:
                if 'error' in resource.status:
                    if delete_on_error:
                        resource.delete()
                    return False
                time.sleep(constants.REFRESH_TIME)
                resource.refresh()
        except exception.NotFound:
            resource._ovo.status = 'deleted'
            resource._ovo.deleted = True
            return False
        return True

    def _validate_requirements(self, request, context):
        vol_caps = capabilities_lib.Capabilities(request.volume_capabilities)
        error = self.service_capabilities.unsupported(vol_caps)
        if error:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, error)

    def _create_volume(self, name, vol_size, request, context, **params):
        vol = self.backend.create_volume(size=vol_size, name=name, **params)
        return vol

    @common.debuggable
    @common.logrpc
    @common.require('name', 'volume_capabilities')
    @common.Worker.unique('name')
    def CreateVolume(self, request, context):
        vol_size, min_size, max_size = self._calculate_size(request, context)
        self._validate_requirements(request, context)

        # NOTE(geguileo): Any reason to support controller_create_secrets?

        # See if the volume is already in the persistence storage
        vol = self._get_vol(volume_name=request.name)

        # If we have multiple references there's something wrong, either the
        # same DB used for multiple purposes and there is a collision name, or
        # there's been a race condition, so we cannot be idempotent, create a
        # new volume.
        if isinstance(vol, cinderlib.Volume):
            LOG.debug('Volume %s exists with id %s' % (request.name, vol.id))
            if not (min_size <= vol.size <= max_size):
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Volume already exists but is incompatible')

            # Other thread/node is creating the volume
            if vol.status == 'creating':
                self._wait(vol, ('available',))

        else:
            # Create volume
            LOG.debug('Creating volume %s' % request.name)
            # Extract parameters
            caps = capabilities_lib.Capabilities(request.volume_capabilities)
            params = self._convert_volume_params(request, caps, context)
            vol = self._create_volume(request.name, vol_size, request, context,
                                      **params)

        if vol.status != 'available':
            context.abort(grpc.StatusCode.ABORTED,
                          'Operation pending for volume (%s)' % vol.status)

        volume = self._convert_volume_type(vol)
        return self.TYPES.CreateResp(volume=volume)

    def _convert_volume_params(self, request, vol_caps, context):
        params = {'qos_specs': {}, 'extra_specs': {},
                  'multiattach': vol_caps.has_multi_mode}
        bad_keys = []

        for k, v in request.parameters.items():
            if k in self.FORBIDDEN_VOL_PARAMS:
                bad_keys.append(k)
            elif k.startswith('qos_'):
                params['qos_specs'][k[4:]] = v
            elif k.startswith('xtra_'):
                params['extra_specs'][k[5:]] = v
            else:
                params[k] = v

        if bad_keys:
            LOG.warning('Ignoring forbidden parameters: %s',
                        ', '.join(bad_keys))

        params.setdefault('metadata', {})
        params['metadata'][CAPS_KEY] = vol_caps.jsons
        return params

    @common.debuggable
    @common.logrpc
    @common.require('volume_id')
    @common.Worker.unique
    def DeleteVolume(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            LOG.debug('Volume %s not found' % request.volume_id)
            return self.DELETE_RESP

        if vol.status == 'in-use':
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Volume in use')

        if (vol.status not in ('available', 'deleting') and
                'error' not in vol.status):
            context.abort(grpc.StatusCode.ABORTED,
                          'Operation pending for volume (%s)' % vol.status)

        if vol.status == 'deleting':
            self._wait(vol, ('deleted',))

        if vol.status != 'deleted':
            LOG.debug('Deleting volume %s' % request.volume_id)
            if vol.snapshots:
                LOG.debug('Volume has snapshots, soft-deleting')
                # Just set the status and not the deleted field so DB
                # persistemce will still return them
                vol._ovo.status = 'deleted'
                vol.save()
            else:
                try:
                    vol.delete()
                except Exception as exc:
                    # TODO(geguileo): Find out what is the right status code
                    #                 for this error
                    context.abort(grpc.StatusCode.UNKNOWN, 'Error: %s' % exc)

        return self.DELETE_RESP

    def _assert_req_cap_matches_vol(self, vol, request):
        vol_caps = capabilities_lib.Capabilities(vol.metadata[CAPS_KEY])
        if all(vol_caps.supports(cap) for cap in request.volume_capabilities):
            return None
        return messages.INCOMPATIBLE_REQUESTED_CAPABILITY

    def check_controller_publish_caps(self, vol, req_cap, node_id, context):
        # We assume that k8s always requests the less restrictive permissions
        # and only makes 1 controller publish call, which is NOT what the
        # CSI spec says, but we are k8s/ocp centric.
        my_conn = self._get_conn(vol, node_id=node_id)

        if my_conn:
            # The spec says we should allow any compatible publish request,
            # but we simplify it, assuming we only get 1 publish.
            if req_cap != self.conn_cap(my_conn):
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              messages.ALREADY_PUBLISHED_CAP)
            return my_conn

        vol_caps = capabilities_lib.Capabilities(vol.metadata[CAPS_KEY])

        # First check that the requested capabilities make sense given the
        # volume created capabilities.
        if not vol_caps.supports(req_cap):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          messages.INCOMPATIBLE_REQUESTED_CAPABILITY)

        # Check if incompatible with existing connections
        err = req_cap.incompatible_connections(vol.connections)
        if err:
            context.abort(*err)

        return None

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'node_id', 'volume_capability')
    @common.Worker.unique
    def ControllerPublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)
        req_cap = capabilities_lib.Capability(request.volume_capability,
                                              ro_forced=request.readonly)

        attach_mode = 'ro' if req_cap.used_as_ro else 'rw'
        conn = self.check_controller_publish_caps(vol, req_cap,
                                                  request.node_id, context)

        if not conn:
            # Abuse the connector dict to store the published capability. We
            # store it in a controller specific location because this
            # connection entry will be used by the node staging.
            connector_dict = node.connector_dict.copy()
            connector_dict[CAP_KEY] = req_cap.json
            vol.connect(connector_dict, attached_host=node.id, mountpoint='',
                        attach_mode=attach_mode)

        return self.TYPES.CtrlPublishResp()

    @common.debuggable
    @common.logrpc
    @common.require('volume_id')
    @common.Worker.unique
    def ControllerUnpublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)
        connections = [conn for conn in vol.connections
                       if conn.attached_host == node.id]
        if connections:
            if len(connections) > 1:
                uuids = [c.instance_uuid for c in connections
                         if c.instance_uuid]
                LOG.warning('The volume was still attached to instances: %s' %
                            ', '.join(uuids))
            for i in range(1, len(connections)):
                conn = connections[i]
                self.backend.persistence.delete_connection(conn)
                vol._connections.remove(conn)
                vol._ovo.volume_attachment.objects.remove(conn._ovo)
            # Do disconnect after removing other connections to ensure it
            # changes to available if there are no more connections.
            connections[0].disconnect()
        return self.CTRL_UNPUBLISH_RESP

    def _paginate(self, request, context, resources):
        resources = sorted(resources, key=lambda res: res.created_at)

        end = len(resources)
        if request.starting_token:
            try:
                marker = common.nano_to_date(request.starting_token)
            except ValueError:
                context.abort(grpc.StatusCode.ABORTED,
                              'Invalid starting_token')

            for i, res in enumerate(resources):
                if res.created_at > marker:
                    start = i
                    break
            else:
                start = end
        else:
            start = 0

        if not resources or start == end:
            return [], None

        if request.max_entries:
            end = min(start + request.max_entries, end)

        selected_resources = itertools.islice(resources, start, end)
        if end < len(resources):
            token = common.date_to_nano(resources[end - 1].created_at)
        else:
            token = None
        return selected_resources, token

    @common.debuggable
    @common.logrpc
    def ListVolumes(self, request, context):
        vols = self._get_vol(always_list=True)
        selected, token = self._paginate(request, context, vols)

        # TODO(geguileo): Once we support volume types set attributes
        entries = [self.TYPES.Entry(volume=self._convert_volume_type(vol))
                   for vol in selected]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return self.TYPES.ListResp(**fields)

    @common.debuggable
    @common.logrpc
    def GetCapacity(self, request, context):
        try:
            self._validate_requirements(request, context)
            # TODO(geguileo): Take into account over provisioning values
            stats = self.backend.stats(refresh=True)
            if 'pools' in stats:
                stats = stats['pools'][0]
            free = stats['free_capacity_gb'] * constants.GB
        except Exception:
            free = 0

        # TODO(geguileo): Confirm available capacity is in bytes
        return self.TYPES.CapacityResp(available_capacity=int(free))

    @common.debuggable
    @common.logrpc
    def ControllerGetCapabilities(self, request, context):
        return self.CTRL_CAPABILITIES_RESP


# As per http://man7.org/linux/man-pages/man5/proc.5.html
class MountInfo(object):
    # Data to return instead of failing
    BAD_MOUNTINFO = ('', '', '', '', '', '', '-', '', '', '')

    def __init__(self, data):
        # Don't fail on bad data, just log it and return whatever we can.
        if isinstance(data, six.string_types):
            data = data.split()
        self.original_data = data

        length = len(data)
        if (length < 10):
            LOG.error('Mount info data is too short: %s', data)
            data = self.BAD_MOUNTINFO

        self.mount_id = data[0]
        self.parent_id = data[1]
        self.st_dev = data[2]
        self.root = data[3]
        self.mount_point = data[4]
        self.mount_options = data[5]

        i = 6
        optional_fields = []
        while i < length and data[i] != '-':
            optional_fields.append(data[i])
            i += 1

        # We must have found the optional fields separator
        if i == length:
            LOG.error('Bad mount info data, missing separator')
            data = self.BAD_MOUNTINFO
            i = 6

        self.optional_fields = optional_fields

        self.fs_type = data[i+1]
        self.mount_source = data[i+2]
        self.super_options = data[i+3]

    @property
    def source(self):
        # Bindmounts will have devtmpfs and we want the root instead
        if self.mount_source.startswith('/'):
            return self.mount_source
        return self.root

    def __str__(self):
        return ('<root: %s, dest: %s, src: %s>' %
                (self.root, self.mount_point, self.mount_source))

    __repr__ = __str__


class NodeBase(IdentityBase):
    STAGED_NAME = 'stage'

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        # When running as Node only we have to initialize cinderlib telling it
        # not to fail when there's no backend configured.
        if persistence_config:
            cinderlib_extra_config = ember_config.copy()
            cinderlib_extra_config.pop('disabled')
            cinderlib_extra_config['fail_on_missing_backend'] = False
            cinderlib.setup(persistence_config=persistence_config,
                            **cinderlib_extra_config)
            IdentityBase.__init__(self, server, ember_config)

        self.node_info = common.NodeInfo.set(node_id, storage_nw_ip)
        self.CSI.add_NodeServicer_to_server(self, server)

        self.STAGE_RESP = self.TYPES.StageResp()
        self.UNSTAGE_RESP = self.TYPES.UnstageResp()
        self.NODE_PUBLISH_RESP = self.TYPES.NodePublishResp()
        self.NODE_UNPUBLISH_RESP = self.TYPES.NodeUnpublishResp()

        capabilities = [
            self.TYPES.NodeCapability(rpc=self.TYPES.NodeRPC(type=rpc))
            for rpc in self.NODE_CAPABILITIES
        ]
        self.NODE_CAPABILITIES_RESP = self.TYPES.NodeCapabilityResp(
            capabilities=capabilities)

    def _get_split_file(self, filename):
        with open(filename) as f:
            result = [line.split() for line in f.read().split('\n') if line]
        return result

    def _get_mountinfo(self):
        return [MountInfo(mount)
                for mount in self._get_split_file('/proc/self/mountinfo')]

    def _vol_private_location(self, volume_id):
        private_bind = os.path.join(defaults.VOL_BINDS_DIR, volume_id)
        return private_bind

    def _get_mount(self, private_bind):
        mounts = self._get_split_file('/proc/self/mounts')
        result = [mount for mount in mounts if mount[0] == private_bind]
        if not result:
            LOG.debug('Private bind %s not found in %s' % (private_bind,
                                                           mounts))
        return result

    def _get_device(self, path):
        """Return the source device for a path.

        The source of a mounted path will either be the mount source of the
        mount point or the root if it's a bind mount.
        """
        mount_info = self._get_mountinfo()
        for mount in mount_info:
            if mount.mount_point == path:
                return mount.source
        LOG.debug('Could not find %s as dest in %s' % (path, mount_info))
        return None

    IS_RO_REGEX = re.compile(r'(^|.+,)ro($|,.+)')

    def _is_ro_mount(self, path):
        for mount in self._get_mountinfo():
            if mount.mount_point == path:
                return bool(self.IS_RO_REGEX.match(mount.mount_options))
        return None

    def _get_vol_device(self, volume_id):
        """Given a volume id return the local device and private bind.

        The private bind is not checked, just returned what it should be if it
        existed.

        The local device is only returned if it exists and it will be a real
        device under /dev.
        """
        private_bind = self._vol_private_location(volume_id)
        device = self._get_device(private_bind)
        return device, private_bind

    def _format_device(self, vol, requested_fs, device, context):
        metadata_fs = self._get_fs_type(vol)

        # We don't use the util-linux Python library to reduce dependencies
        stdout, stderr = self.sudo('lsblk', '-nlfoFSTYPE', device, retries=5,
                                   errors=[1, 32], delay=2)
        fs_types = [line for line in stdout.split() if line]
        current_fs = fs_types[0] if fs_types else None

        if current_fs != metadata_fs:
            LOG.warning("Inconsistent fs-type: %s in metadata, %s in lsblk.  "
                        "Probable cause is that this volume was created from a"
                        " source (snapshot/volume) right between building the "
                        "FS and flushing the data.",
                        metadata_fs, current_fs)

        if current_fs == requested_fs:
            return

        if current_fs:
            context.abort(grpc.StatusCode.ALREADY_EXISTS,
                          'Cannot stage filesystem %s on device that '
                          'already has filesystem %s' %
                          (requested_fs, current_fs))

        cmd = [defaults.MKFS + requested_fs]
        cmd.extend(self.MKFS_ARGS.get(requested_fs, self.DEFAULT_MKFS_ARGS))
        cmd.append(device)
        self.sudo(*cmd)

        # Store that the volume is being used as a mount.
        if metadata_fs != requested_fs:
            self._set_metadata(vol, fs_type=requested_fs)

    def _check_mount_exists(self, capability, private_bind, target, context):
        mounts = self._get_mount(private_bind)
        if mounts:
            if target != mounts[0][1]:
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Filesystem already mounted on %s' %
                              mounts[0][1])

            requested_flags = set(capability.mount.mount_flags or [])
            missing_flags = requested_flags.difference(mounts[0][3].split(','))
            if missing_flags:
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Already mounted with different flags (%s)' %
                              missing_flags)
            return True
        return False

    def _mount(self, fs_type, mount_flags, private_bind, target):
        # Mount must only be called if it's already not mounted
        # We don't use the util-linux Python library to reduce dependencies
        command = ['mount', '-t', fs_type]
        if mount_flags:
            command.append('-o')
            command.append(','.join(mount_flags))
        command.append(private_bind)
        command.append(target)
        self.sudo(*command)

    def _check_path(self, request, context, path, attr='staging'):
        try:
            st_mode = os.stat(os.path.dirname(path)).st_mode
        except OSError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          "Parent %s directory for %s doesn't exist: %s" %
                          (attr, path, exc))

        # Parent must always be a directory
        if not stat.S_ISDIR(st_mode):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Parent %s path %s is not a directory' %
                          (attr, path))

        is_block = request.volume_capability.HasField('block')

        try:
            st_mode = os.stat(path).st_mode
            if ((is_block and
                 not (stat.S_ISBLK(st_mode) or stat.S_ISREG(st_mode))) or
                    (not is_block and not stat.S_ISDIR(st_mode))):

                context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                              'Invalid existing %s path %s' % (attr, path))
        except OSError as exc:
            if is_block:
                # Create the bind file
                open(path, 'a').close()
            else:
                # Create the directory for bind mounting
                os.mkdir(path)
        return is_block

    def _check_staging_path(self, request, context):
        path = os.path.join(request.staging_target_path, self.STAGED_NAME)
        is_block = self._check_path(request, context, path)
        return path, is_block

    def _check_target_path(self, request, context):
        path = request.target_path
        self._check_path(request, context, path, 'publish')
        return path

    def check_node_stage_caps(self, vol, target, request, context):
        # We assume we only have 1 publish request per stage request and that
        # the capabilities match.
        conn = self._get_conn(vol, path=target, alt_path='')

        if not conn:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          messages.NOT_PUBLISHED_CAPS)

        con_cap = self.conn_cap(conn)
        # Staging capability doesn't come with readonly parameter, so we just
        # copy it from the published one.
        req_cap = capabilities_lib.Capability(request.volume_capability,
                                              con_cap.ro_forced)

        if not con_cap.supports(req_cap):
            context.abort(grpc.StatusCode.ALREADY_EXISTS,
                          messages.INCOMPATIBLE_CAP_PATH)

        # If we were implementing CSI as it is defined in the spec, where
        # RWO+ROX mode is supported we would have to check that there's only
        # one writer for that case, but k8s doesn't support that mode.

        # We would also have to check if we have an incompatible staged or
        # published volume in this or other nodes.  Including checking if we
        # are staging twice (different paths) on this node with RWO.

        # This should select a compatible published connection, but we
        # simplified it, as we assume we only get 1 publish call, and 1 stage
        # call for it.
        return conn

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path', 'volume_capability')
    @common.Worker.unique
    def NodeStageVolume(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)
        target, is_block = self._check_staging_path(request, context)
        conn = self.check_node_stage_caps(vol, target, request, context)

        device, private_bind = self._get_vol_device(vol.id)
        if not device:
            # Some slow systems may take a while to detect the multipath so we
            # retry the attach.  Since we don't disconnect this will go fast
            # through the login phase.
            for i in range(constants.MULTIPATH_FIND_RETRIES):
                conn.attach()
                if not conn.use_multipath or conn.path.startswith('/dev/dm'):
                    break
                LOG.debug('Retrying to get a multipath')
            # Create the private bind file
            open(private_bind, 'a').close()
            # TODO(geguileo): make path for private binds configurable
            self.sudo('mount', '--bind', conn.path, private_bind)
            device = conn.path

        if is_block:
            # Avoid multiple binds if CO incorrectly called us twice
            device = self._get_device(target)
            if not device:
                # TODO(geguileo): Add support for NFS/QCOW2
                # Create the staging file for bind mounting
                open(target, 'a').close()
                self.sudo('mount', '--bind', private_bind, target)
        else:
            if not self._check_mount_exists(request.volume_capability,
                                            private_bind, target, context):
                fs_type = (request.volume_capability.mount.fs_type or
                           CONF.DEFAULT_MOUNT_FS)
                self._format_device(vol, fs_type, private_bind, context)
                flags = request.volume_capability.mount.mount_flags
                self._mount(fs_type, flags, private_bind, target)

        if not conn.mountpoint:
            conn._ovo.mountpoint = target
            conn.save()
        return self.STAGE_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path')
    @common.Worker.unique
    def NodeUnstageVolume(self, request, context):
        # TODO(geguileo): Add support for NFS/QCOW2
        vol = self._get_vol(request.volume_id, context=context)
        device, private_bind = self._get_vol_device(vol.id)
        # If it's not already unstaged
        expected = (device, private_bind)
        if device:
            do_match = [mount for mount in self._get_mountinfo()
                        if mount.source in expected]
            count = len(do_match)

            # If the volume is still in use we cannot unstage (one use is for
            # our private volume reference and the other for staging path)
            if count > 2:
                LOG.debug('Volume still in use. Mountpoints: %s' % do_match)
                context.abort(grpc.StatusCode.ABORTED,
                              'Operation pending for volume')

            staging_path = os.path.join(request.staging_target_path,
                                        self.STAGED_NAME)
            if count == 2:
                self.sudo('umount', staging_path, retries=4)
                self._clean_file_or_dir(staging_path)
            if count > 0:
                self.sudo('umount', private_bind, retries=4)
            os.remove(private_bind)

            conn = self._get_conn(vol, path=staging_path)
            if conn:
                conn.detach()
                conn._ovo.mountpoint = ''
                conn.save()

        return self.UNSTAGE_RESP

    def _clean_file_or_dir(self, path):
        # For UnStage we need to remove the file we created or kubelet will
        # fail.  For UnPublish the spec says we need to remove it as well.
        try:
            if os.path.isfile(path):
                os.remove(path)
            else:
                os.rmdir(path)
        except OSError as exc:
            LOG.warning('Could not remove %s: %s' % (path, exc))

    def check_node_publish_caps(self, vol, staging, target, request, context):
        stage_conn = self._get_conn(vol, path=staging)
        conn = self._get_conn(vol, path=target) or stage_conn
        if not conn:
            return None, None

        pod_uid = self._get_pod_uid(request)
        req_cap = capabilities_lib.Capability(request.volume_capability,
                                              request.readonly)

        if staging == conn.mountpoint:
            # Check if requested capability is compatible with existing ones
            err = req_cap.incompatible_connections(vol.connections,
                                                   exclude=[conn, stage_conn])
            if err:
                context.abort(*err)

            # We need to duplicate the staging connection obj for the publish
            attach_mode = 'ro' if req_cap.used_as_ro else 'rw'
            conn = self._duplicate_connection(vol, conn, req_cap, attach_mode,
                                              mountpoint=target,
                                              instance_uuid=pod_uid)

        else:
            if req_cap != self.conn_cap(conn):
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              messages.INCOMPATIBLE_CAP_PATH)

            if pod_uid != conn.instance_uuid:
                if conn.instance_uuid:
                    LOG.warnning('Reusing connector from instance %s for %s'
                                 (conn.instance_uuid, pod_uid))
                conn._ovo.instance_uuid = pod_uid
                conn.save()

        return conn, req_cap

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path', 'target_path',
                    'volume_capability')
    @common.Worker.unique
    def NodePublishVolume(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)
        staging_target, is_block = self._check_staging_path(request, context)
        target = self._check_target_path(request, context)

        # Check that the staging has been done.  We must have the device
        # attached and the connection must exist, be it a node publish
        # connection or a staging one.
        volume_device, private_bind = self._get_vol_device(request.volume_id)
        error = (not volume_device or
                 (is_block and not self._get_device(staging_target)) or
                 (not is_block and
                  not self._check_mount_exists(request.volume_capability,
                                               private_bind, staging_target,
                                               context)))

        conn, req_cap = self.check_node_publish_caps(vol, staging_target,
                                                     target, request, context)

        if error or not conn:
            LOG.debug('Failing because error=%s and conn=%s' % (error, conn))
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Staging has not been successfully called')

        # Check if it's already attached.  We do it like this instead of just
        # checking the conn.mountpoint to be sure we physically have it,
        # because a duplicated connection would have the field set from the
        # start.
        device = self._get_device(target)
        if device in (volume_device, staging_target, private_bind):
            # No need to check readonly mocde here it was checked before
            return self.NODE_PUBLISH_RESP

        # If not published bind it
        mount_options = 'bind,ro' if req_cap.used_as_ro else 'bind'
        self.sudo('mount', '-o', mount_options, staging_target, target)

        return self.NODE_PUBLISH_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'target_path')
    @common.Worker.unique
    def NodeUnpublishVolume(self, request, context):
        device = self._get_device(request.target_path)
        if device:
            # NOTE: According to k8s e2e csi tests they expect the data to be
            # flushed after the unpublish, but in our case it wouldn't be until
            # the unstage, so we have to force the sync here.
            vol_dev = self._vol_private_location(request.volume_id)
            self.sudo('sync', vol_dev)
            self.sudo('umount', request.target_path, retries=4)
            self._clean_file_or_dir(request.target_path)
        vol = self._get_vol(request.volume_id)
        conn = self._get_conn(vol, path=request.target_path)
        if conn:
            # We remove the connection since this was unique to this publish
            # call, and the controller uses the one from staging
            cinderlib.Backend.persistence.delete_connection(conn)
            vol._connections.remove(conn)
            vol._ovo.volume_attachment.objects.remove(conn._ovo)
        return self.NODE_UNPUBLISH_RESP

    @common.debuggable
    @common.logrpc
    def NodeGetCapabilities(self, request, context):
        return self.NODE_CAPABILITIES_RESP


class TopologyBase(object):
    GRPC_TOPOLOGIES = None
    TOPOLOGY_HIERA = None

    def _init_topology(self, constraint_type):
        if CONF.TOPOLOGIES:
            if constraint_type not in self.PLUGIN_CAPABILITIES:
                self.PLUGIN_CAPABILITIES.append(constraint_type)

            hiera = {}
            grpc_topos = []

            for topology in CONF.TOPOLOGIES:
                level = hiera
                for segment_name, segment_value in topology.items():
                    value = level.setdefault(segment_name, {})
                    level = value.setdefault(segment_value, {})
                grpc_topos.append(self.TYPES.Topology(segments=topology))

            self.TOPOLOGY_HIERA = hiera
            self.GRPC_TOPOLOGIES = grpc_topos

    def _topology_is_accessible(self, topology, context):
        unchecked = list(topology.segments.keys())
        level = self.TOPOLOGY_HIERA
        while level and unchecked:
            for segment_name in level:
                if segment_name in unchecked:
                    value = topology.segments[segment_name]
                    level = level[segment_name].get(value)
                    unchecked.remove(segment_name)
                    break

        # Accessible if value of a segment name didn't fail, and if one of the
        # topologies is a subset of the other one.
        return level is not None and not (unchecked and level)
        # return not (levels is None or (unchecked_segments and level))

    def _validate_accessible_requirements(self, topology_req, context):
        requisite = getattr(topology_req, 'requisite', None)
        preferred = getattr(topology_req, 'preferred', None)
        if not (requisite or preferred):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Need topology requisite and/or preferred field')

        # preferrend must be a subset of requisite
        if requisite and preferred:
            for p in preferred:
                if p not in requisite:
                    context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                                  'All preferred topologies must be in '
                                  'requisite topologies')

        # If we only have preferred, we can ignore it, after all we don't have
        # different topologies to choose from.
        if not requisite:
            return

        for topology in requisite:
            if self._topology_is_accessible(topology, context):
                return

        context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                      'None of the requested topologies are accessible.')

    def _validate_accessibility(self, request, context):
        if not self.GRPC_TOPOLOGIES:
            return

        # Used by CreateVolume
        if (hasattr(request, 'accessibility_requirements') and
                request.HasField('accessibility_requirements')):
            self._validate_accessible_requirements(
                request.accessibility_requirements, context)

        # Used by GetCapacity
        if (hasattr(request, 'accessible_topology') and
                request.HasField('accessible_topology')):
            # TODO(geguileo): Check request.accessible_topology for GetCapacity
            if not self._topology_is_accessible(request.accessible_topology,
                                                context):
                context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                              'Topology is not accessible.')


class SnapshotBase(object):
    def _get_snap(self, snapshot_id=None, always_list=False, **filters):
        res = self.persistence.get_snapshots(
            snapshot_id=snapshot_id, **filters)
        if (not always_list and
                (res and len(res) == 1 and (snapshot_id or filters))):
            return res[0]
        return res

    def _create_from_snap(self, snap_id, vol_size, name, context, **params):
        src_snap = self._get_snap(snap_id)
        if not src_snap:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Snapshot %s does not exist' % snap_id)
        if src_snap.status != 'available':
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Snapshot %s is not available' % snap_id)
        if src_snap.volume_size > vol_size:
            context.abort(grpc.StatusCode.OUT_OF_RANGE,
                          'Snapshot %s is bigger than requested volume' %
                          snap_id)
        vol = src_snap.create_volume(name=name, size=vol_size, **params)
        return vol

    # Inheriting classes must implement
    # def _convert_snapshot_type(self, snap):
    @common.debuggable
    @common.logrpc
    @common.require('name', 'source_volume_id')
    @common.Worker.unique('name')
    def CreateSnapshot(self, request, context):
        snap = self._get_snap(snapshot_name=request.name)

        # If we have multiple references there's something wrong, either the
        # same DB used for multiple purposes and there is a collision name, or
        # there's been a race condition, so we cannot be idempotent, create a
        # new snapshot.
        if isinstance(snap, cinderlib.Snapshot):
            if request.source_volume_id != snap.volume_id:
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Snapshot %s from %s exists for volume %s' %
                              (request.name, request.source_volume_id,
                               snap.volume_id))
            LOG.debug('Snapshot %s exists with id %s' % (request.name,
                                                         snap.id))
        else:
            vol = self._get_vol(request.source_volume_id, context=context)
            snap = vol.create_snapshot(name=request.name)
        snapshot = self._convert_snapshot_type(snap)
        return self.TYPES.CreateSnapResp(snapshot=snapshot)

    @common.debuggable
    @common.logrpc
    @common.require('snapshot_id')
    @common.Worker.unique('snapshot_id')
    def DeleteSnapshot(self, request, context):
        snap = self._get_snap(request.snapshot_id)
        if snap:
            snap.delete()
            if snap.volume.status == 'deleted' and not snap.volume.snapshots:
                LOG.debug('Last snapshot deleted, deleting soft-deleted '
                          'volume %s' % snap.volume.id)
                snap.volume.delete()
        return self.DELETE_SNAP_RESP

    @common.debuggable
    @common.logrpc
    def ListSnapshots(self, request, context):
        if not (request.source_volume_id or request.snapshot_id):
            vols = self._get_vol()
            snaps = []
            for v in vols:
                snaps.extend(self._get_snap(volume_id=v.id, always_list=True))
        else:
            snaps = self._get_snap(snapshot_id=request.snapshot_id,
                                   volume_id=request.source_volume_id,
                                   always_list=True)

        selected, token = self._paginate(request, context, snaps)

        entries = [
            self.TYPES.SnapEntry(snapshot=self._convert_snapshot_type(snap))
            for snap in selected]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return self.TYPES.ListSnapResp(**fields)

    def _unimplemented(self, request, context, *args, **kwargs):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def _disable_features(self, features):
        if constants.SNAPSHOT_FEATURE not in features:
            return

        for capab in (self.TYPES.CtrlCapabilityType.CREATE_DELETE_SNAPSHOT,
                      self.TYPES.CtrlCapabilityType.LIST_SNAPSHOTS):
            if capab in self.CTRL_CAPABILITIES:
                self.CTRL_CAPABILITIES.remove(capab)

        self.CreateSnapshot = self._unimplemented
        self.DeleteSnapshot = self._unimplemented
        self.ListSnapshots = self._unimplemented
