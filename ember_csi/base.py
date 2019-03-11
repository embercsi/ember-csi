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
import time

import cinderlib
from cinderlib import exception
import grpc
from oslo_concurrency import processutils as putils
from oslo_log import log as logging

from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi import defaults


CONF = config.CONF
LOG = logging.getLogger(__name__)


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

    def __init__(self, server, cinderlib_cfg):
        # Skip if we've already been initialized (happens on class All)
        if self.manifest is not None:
            return

        self.csi_version = version.StrictVersion(CONF.CSI_SPEC)
        self.PLUGIN_CAPABILITIES.append(
            self.TYPES.ServiceType.CONTROLLER_SERVICE)
        caps = [self.TYPES.Capability(service=self.TYPES.Service(type=t))
                for t in self.PLUGIN_CAPABILITIES]
        self.PLUGIN_CAPABILITIES_RESP = self.TYPES.CapabilitiesResp(
            capabilities=caps)

        self.root_helper = ((cinderlib_cfg or {}).get('root_helper') or
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
        # NOTE(geguileo): For now let's only support single reader/writer modes
        self.SUPPORTED_ACCESS = (
            self.TYPES.AccessModeType.SINGLE_NODE_WRITER,
            self.TYPES.AccessModeType.SINGLE_NODE_READER_ONLY)

        self.CSI.add_IdentityServicer_to_server(self, server)
        self.manifest = manifest
        self.PROBE_KV = cinderlib.objects.KeyValue('%s.%s.%s.%s' % (
            CONF.NAME, CONF.MODE, socket.getfqdn(), 'probe'), '0')

    def _unsupported_mode(self, capability):
        return capability.access_mode.mode not in self.SUPPORTED_ACCESS

    def _unsupported_fs_type(self, capability):
        # TODO: validate mount_flags
        return (capability.HasField('mount') and
                capability.mount.fs_type and
                capability.mount.fs_type not in CONF.SUPPORTED_FS_TYPES)

    def _validate_capabilities(self, capabilities, context=None):
        msg = ''

        for capability in capabilities:
            # TODO(geguileo): Find out what is the right status code
            if self._unsupported_mode(capability):
                msg = 'Unsupported access mode'
                break

            if self._unsupported_fs_type(capability):
                msg = 'Unsupported file system type'
                break

        if context and msg:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)

        return msg

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

    def _get_vol(self, volume_id=None, always_list=False, **filters):
        backend_name = self.backend.id if self.backend else None
        res = self.persistence.get_volumes(
            volume_id=volume_id, backend_name=backend_name, **filters)
        # Ignore soft-deleted volumes
        res = [vol for vol in res if vol.status != 'deleted']
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


class ControllerBase(IdentityBase):
    FORBIDDEN_VOL_PARAMS = ('id', 'name', 'size', 'volume_size')

    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, **kwargs):
        cinderlib.setup(persistence_config=persistence_config,
                        **ember_config)
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

    def _get_size(self, what, request, default):
        vol_size = getattr(request.capacity_range, what + '_bytes', None)
        if vol_size:
            return vol_size / constants.GB
        return default

    def _calculate_size(self, request, context):
        # Must be idempotent
        min_size = self._get_size('required', request, defaults.VOLUME_SIZE)
        max_size = self._get_size('limit', request, min_size)
        if max_size < min_size:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Limit_bytes is greater than required_bytes')

        vol_size = min(min_size, max_size)

        if vol_size < 1:
            if max_size < 1:
                context.abort(grpc.StatusCode.OUT_OF_RANGE,
                              'Unsupported capacity_range (min size is 1GB)')
            vol_size = max_size
        return (vol_size, min_size, max_size)

    def _get_vol_node(self, request, context):
        if request.node_id:
            node = common.NodeInfo.get(request.node_id)
            if not node:
                context.abort(grpc.StatusCode.NOT_FOUND,
                              'Node %s does not exist' % request.node_id)
        else:
            node = None

        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

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
        self._validate_capabilities(request.volume_capabilities, context)

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
            params = self._convert_volume_params(request, context)
            vol = self._create_volume(request.name, vol_size, request, context,
                                      **params)

        if vol.status != 'available':
            context.abort(grpc.StatusCode.ABORTED,
                          'Operation pending for volume (%s)' % vol.status)

        volume = self._convert_volume_type(vol)
        return self.TYPES.CreateResp(volume=volume)

    def _convert_volume_params(self, request, context):
        params = {'qos_specs': {}, 'extra_specs': {}}
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

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'node_id', 'volume_capability')
    @common.Worker.unique
    def ControllerPublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)

        # The volume is already attached
        if vol.status == 'in-use':
            for conn in vol.connections:
                # TODO(geguileo): Change when we enable multi-attach
                if conn.attached_host != request.node_id:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                                  'Volume published to another node')
                expected_mode = 'ro' if request.readonly else 'rw'
                if conn.attach_mode != expected_mode:
                    context.abort(grpc.StatusCode.ALREADY_EXISTS,
                                  'Volume published with readonly=%s. Cannot '
                                  'publish now as readonly=%s' %
                                  (not request.readonly, request.readonly))
        else:
            c = vol.connect(node.connector_dict, attached_host=node.id)
            # TODO(geguileo): Once cinderlib supports changing attach_mode on
            # the connect call pass it there and remove this.
            if request.readonly:
                c._ovo.attach_mode = 'ro'
                c.save()
        return self.TYPES.CtrlPublishResp()

    @common.debuggable
    @common.logrpc
    @common.require('volume_id')
    @common.Worker.unique
    def ControllerUnpublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)
        for conn in vol.connections:
            if node is None or conn.attached_host == node.id:
                conn.disconnect()
        return self.CTRL_UNPUBLISH_RESP

    def _paginate(self, request, context, resources):
        resources = sorted(resources, key=lambda res: res.created_at)

        if not resources:
            return [], None

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
            start = 0

        end = len(resources)
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
        self._validate_requirements(request, context)
        # TODO(geguileo): Take into account over provisioning values
        stats = self.backend.stats(refresh=True)
        if 'pools' in stats:
            stats = stats['pools'][0]
        free = stats['free_capacity_gb'] * constants.GB

        # TODO(geguileo): Confirm available capacity is in bytes
        return self.TYPES.CapacityResp(available_capacity=int(free))

    @common.debuggable
    @common.logrpc
    def ControllerGetCapabilities(self, request, context):
        return self.CTRL_CAPABILITIES_RESP


class NodeBase(IdentityBase):
    STAGED_NAME = 'stage'

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        # When running as Node only we have to initialize cinderlib telling it
        # not to fail when there's no backend configured.
        if persistence_config:
            ember_config['fail_on_missing_backend'] = False
            cinderlib.setup(persistence_config=persistence_config,
                            **ember_config)
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
        return self._get_split_file('/proc/self/mountinfo')

    def _vol_private_location(self, volume_id):
        private_bind = os.path.join(defaults.VOL_BINDS_DIR, volume_id)
        return private_bind

    def _get_mount(self, private_bind):
        mounts = self._get_split_file('/proc/self/mounts')
        result = [mount for mount in mounts if mount[0] == private_bind]
        return result

    def _get_device(self, path):
        for line in self._get_mountinfo():
            if line[4] == path:
                return line[9] if line[9].startswith('/') else line[3]
        return None

    IS_RO_REGEX = re.compile(r'(^|.+,)ro($|,.+)')

    def _is_ro_mount(self, path):
        for line in self._get_mountinfo():
            if line[4] == path:
                return bool(self.IS_RO_REGEX.match(line[5]))
        return None

    def _get_vol_device(self, volume_id):
        private_bind = self._vol_private_location(volume_id)
        device = self._get_device(private_bind)
        return device, private_bind

    def _format_device(self, fs_type, device, context):
        # We don't use the util-linux Python library to reduce dependencies
        stdout, stderr = self.sudo('lsblk', '-nlfoFSTYPE', device, retries=5,
                                   errors=[1, 32], delay=2)
        fs_types = filter(None, stdout.split())
        if fs_types:
            if fs_types[0] == fs_type:
                return
            context.abort(grpc.StatusCode.ALREADY_EXISTS,
                          'Cannot stage filesystem %s on device that '
                          'already has filesystem %s' %
                          (fs_type, fs_types[0]))
        cmd = [defaults.MKFS + fs_type]
        cmd.extend(self.MKFS_ARGS.get(fs_type, self.DEFAULT_MKFS_ARGS))
        cmd.append(device)
        self.sudo(*cmd)

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

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path', 'volume_capability')
    @common.Worker.unique
    def NodeStageVolume(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

        self._validate_capabilities([request.volume_capability], context)
        target, is_block = self._check_staging_path(request, context)

        device, private_bind = self._get_vol_device(vol.id)
        if not device:
            conn = vol.connections[0]
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
                self._format_device(fs_type, private_bind, context)
                self._mount(fs_type,
                            request.volume_capability.mount.mount_flags,
                            private_bind, target)
        return self.STAGE_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path')
    @common.Worker.unique
    def NodeUnstageVolume(self, request, context):
        # TODO(geguileo): Add support for NFS/QCOW2
        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

        device, private_bind = self._get_vol_device(vol.id)
        # If it's not already unstaged
        if device:
            count = 0
            for line in self._get_mountinfo():
                if line[3] in (device, private_bind):
                    count += 1

            if self._get_mount(private_bind):
                count += 1

            # If the volume is still in use we cannot unstage (one use is for
            # our private volume reference and the other for staging path
            if count > 2:
                context.abort(grpc.StatusCode.ABORTED,
                              'Operation pending for volume')

            if count == 2:
                path = os.path.join(request.staging_target_path,
                                    self.STAGED_NAME)
                self.sudo('umount', path, retries=4)
                self._clean_file_or_dir(path)
            if count > 0:
                self.sudo('umount', private_bind, retries=4)
            os.remove(private_bind)

            conn = vol.connections[0]
            conn.detach()

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

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path', 'target_path',
                    'volume_capability')
    @common.Worker.unique
    def NodePublishVolume(self, request, context):
        self._validate_capabilities([request.volume_capability], context)
        staging_target, is_block = self._check_staging_path(request, context)

        device, private_bind = self._get_vol_device(request.volume_id)
        error = (not device or
                 (is_block and not self._get_device(staging_target)) or
                 (not is_block and
                  not self._check_mount_exists(request.volume_capability,
                                               private_bind, staging_target,
                                               context)))
        if error:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Staging was not been successfully called')

        target = self._check_target_path(request, context)

        # TODO(geguileo): Add support for modes, etc.

        # Check if it's already published
        device = self._get_device(target)
        volume_device, private_bind = self._get_vol_device(request.volume_id)
        if device in (volume_device, staging_target, private_bind):
            ro_mode = self._is_ro_mount(target)
            if request.readonly != ro_mode:
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Incompatible readonly=%s mode requested, volume'
                              'is already present as %s' %
                              (request.readonly, ro_mode))

            return self.NODE_PUBLISH_RESP

        # TODO(geguileo): Check how many are mounted and fail if > 0

        # If not published bind it
        mount_options = 'bind,ro' if request.readonly else 'bind'
        self.sudo('mount', '-o', mount_options, staging_target, target)
        return self.NODE_PUBLISH_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'target_path')
    @common.Worker.unique
    def NodeUnpublishVolume(self, request, context):
        device = self._get_device(request.target_path)
        if device:
            self.sudo('umount', request.target_path, retries=4)
            self._clean_file_or_dir(request.target_path)
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
        vol = src_snap.create_volume(name=name, **params)
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
            vol = self._get_vol(request.source_volume_id)
            if not vol:
                context.abort(grpc.StatusCode.NOT_FOUND,
                              'Volume %s does not exist' % request.volume_id)
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
