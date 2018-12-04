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
import itertools
import json
import os
import re
import socket
import stat
import sys
import time

import cinderlib
from builtins import int
import grpc
from os_brick.initiator import connector as brick_connector
from oslo_concurrency import processutils as putils

from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi import defaults
from ember_csi.v0_2_0 import csi_pb2_grpc as csi
from ember_csi.v0_2_0 import csi_types as types


class NodeInfo(object):
    __slots__ = ('id', 'connector_dict')

    def __init__(self, node_id, connector_dict):
        self.id = node_id
        self.connector_dict = connector_dict

    @classmethod
    def get(cls, node_id):
        kv = cinderlib.Backend.persistence.get_key_values(node_id)
        if not kv:
            return None
        return cls(node_id, json.loads(kv[0].value))

    @classmethod
    def set(cls, node_id, storage_nw_ip):
        # For now just set multipathing and not enforcing it
        connector_dict = brick_connector.get_connector_properties(
            'sudo', storage_nw_ip, config.REQUEST_MULTIPATH, False)
        value = json.dumps(connector_dict, separators=(',', ':'))
        kv = cinderlib.KeyValue(node_id, value)
        cinderlib.Backend.persistence.set_key_value(kv)
        return NodeInfo(node_id, connector_dict)


class Identity(csi.IdentityServicer):
    backend = None
    # NOTE(geguileo): For now let's only support single reader/writer modes
    SUPPORTED_ACCESS = (types.AccessModeType.SINGLE_NODE_WRITER,
                        types.AccessModeType.SINGLE_NODE_READER_ONLY)
    PROBE_RESP = types.ProbeResp()
    CAPABILITIES = types.CapabilitiesResponse(
        [types.ServiceType.CONTROLLER_SERVICE])
    manifest = None
    MKFS = defaults.MKFS
    DEFAULT_MKFS_ARGS = tuple()
    MKFS_ARGS = {'ext4': ('-F',)}

    def __init__(self, server, cinderlib_cfg, plugin_name):
        if self.manifest is not None:
            return

        self.root_helper = (cinderlib_cfg or {}).get('root_helper') or 'sudo'

        manifest = {
            'cinderlib-version': cinderlib.__version__,
            'cinder-version': constants.CINDER_VERSION,
        }
        self.persistence = cinderlib.Backend.persistence
        manifest['persistence'] = type(self.persistence).__name__

        manifest['mode'] = type(self).__name__.lower()

        if self.backend:
            manifest['cinder-driver-version'] = self.backend.get_version()
            manifest['cinder-driver'] = type(self.backend.driver).__name__
            manifest['cinder-driver-supported'] = str(self.backend.supported)

        self.plugin_name = self._validate_name(plugin_name)
        self.INFO = types.InfoResp(name=self.plugin_name,
                                   vendor_version=constants.VENDOR_VERSION,
                                   manifest=manifest)

        csi.add_IdentityServicer_to_server(self, server)
        self.manifest = manifest

    def _unsupported_mode(self, capability):
        return capability.access_mode.mode not in self.SUPPORTED_ACCESS

    def _unsupported_fs_type(self, capability):
        # TODO: validate mount_flags
        return (capability.HasField('mount') and
                capability.mount.fs_type and
                capability.mount.fs_type not in config.SUPPORTED_FS_TYPES)

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
        return self.CAPABILITIES

    @common.debuggable
    @common.logrpc
    def Probe(self, request, context):
        failure = False
        # check configuration
        # check_persistence
        if self.backend:
            # check driver
            pass

        if failure:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Persistence is not accessible')

        return self.PROBE_RESP

    def _get_vol(self, volume_id=None, **filters):
        backend_name = self.backend.id if self.backend else None
        res = self.persistence.get_volumes(
            volume_id=volume_id, backend_name=backend_name, **filters)
        if res and len(res) == 1 and (volume_id or filters):
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


class Controller(csi.ControllerServicer, Identity):
    CTRL_UNPUBLISH_RESP = types.UnpublishResp()
    DELETE_RESP = types.DeleteResp()
    DELETE_SNAP_RESP = types.DeleteSnapResp()

    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, **kwargs):
        plugin_name = ember_config.pop('plugin_name', None)
        cinderlib.setup(persistence_config=persistence_config,
                        **ember_config)
        self.backend = cinderlib.Backend(**backend_config)
        Identity.__init__(self, server, ember_config, plugin_name)
        csi.add_ControllerServicer_to_server(self, server)

    def _get_size(self, what, request, default):
        vol_size = getattr(request.capacity_range, what + '_bytes', None)
        if vol_size:
            return vol_size / constants.GB
        return default

    def _wait(self, vol, states, delete_on_error=False):
        # TODO(geguileo): Introduce timeout and probably cleanup mechanism
        status = vol.status
        while status not in states:
            if 'error' in vol.status:
                if delete_on_error:
                    vol.delete()
                return False
            time.sleep(constants.REFRESH_TIME)
            vol = self._get_vol(vol.id)
            status = vol.status if vol else 'deleted'
        return True

    def _get_vol_node(self, request, context):
        if request.node_id:
            node = NodeInfo.get(request.node_id)
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

    def _get_snap(self, snapshot_id=None, **filters):
        res = self.persistence.get_snapshots(
            snapshot_id=snapshot_id, **filters)
        if res and len(res) == 1 and (snapshot_id or filters):
            return res[0]
        return res

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

    @common.debuggable
    @common.logrpc
    @common.require('name', 'volume_capabilities')
    @common.Worker.unique('name')
    def CreateVolume(self, request, context):
        vol_size, min_size, max_size = self._calculate_size(request, context)

        self._validate_capabilities(request.volume_capabilities, context)

        # TODO(geguileo): Use request.parameters for vol type extra specs and
        #                 return volume_attributes to reflect parameters used.
        # NOTE(geguileo): Any reason to support controller_create_secrets?

        # See if the volume is already in the persistence storage
        vol = self._get_vol(volume_name=request.name)

        # If we have multiple references there's something wrong, either the
        # same DB used for multiple purposes and there is a collision name, or
        # there's been a race condition, so we cannot be idempotent, create a
        # new volume.
        if isinstance(vol, cinderlib.Volume):
            print('Volume %s exists with id %s' % (request.name, vol.id))
            if not (min_size <= vol.size <= max_size):
                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Volume already exists but is incompatible')

            # Other thread/node is creating the volume
            if vol.status == 'creating':
                self._wait(vol, ('available',))

            elif vol.status != 'available':
                context.abort(grpc.StatusCode.ABORTED,
                              'Operation pending for volume (%s)' % vol.status)

        else:
            # Create volume
            print('creating volume')
            if request.HasField('volume_content_source'):
                snap_id = request.volume_content_source.snapshot.id
                snap = self._get_snap(snap_id)
                if not snap:
                    context.abort(grpc.StatusCode.NOT_FOUND,
                                  'Snapshot %s does not exist' %
                                  request.snapshot_id)
                vol = snap.create_volume(name=request.name)
            else:
                vol = self.backend.create_volume(size=vol_size,
                                                 name=request.name)

        volume = types.Volume(capacity_bytes=int(vol.size * constants.GB),
                              id=vol.id,
                              attributes=request.parameters)
        return types.CreateResp(volume=volume)

    @common.debuggable
    @common.logrpc
    @common.require('volume_id')
    @common.Worker.unique
    def DeleteVolume(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            print('Volume not found')
            return self.DELETE_RESP

        if vol.status == 'deleting':
            self._wait(vol, ('deleted',))

        if vol.status == 'in-use':
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Volume in use')

        if vol.status != 'available' and 'error' not in vol.status:
            context.abort(grpc.StatusCode.ABORTED,
                          'Operation pending for volume (%s)' % vol.status)

        print('Deleting volume')
        try:
            vol.delete()
        except Exception as exc:
            # TODO(geguileo): Find out what is the right status code for this
            #                 error
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

            mode = request.volume_capability.access_mode.mode
            if ((not request.readonly and
                 mode == types.AccessModeType.SINGLE_NODE_READER_ONLY) or
                    (request.readonly and
                     mode == types.AccessModeType.SINGLE_NODE_WRITER)):  # noqa

                context.abort(grpc.StatusCode.ALREADY_EXISTS,
                              'Readonly incompatible with volume capability')

            conn = vol.connections[0]
        else:
            conn = vol.connect(node.connector_dict, attached_host=node.id)
        publish_info = {'connection_info': json.dumps(conn.connection_info)}
        return types.CtrlPublishResp(publish_info=publish_info)

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

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_capabilities')
    def ValidateVolumeCapabilities(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

        message = self._validate_capabilities(request.volume_capabilities)
        # TODO(geguileo): Add support for attributes via volume types
        if not message and request.volume_attributes:
            message = "Parameters don't match"

        return types.ValidateResp(supported=not bool(message), message=message)

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
        vols = self._get_vol()
        selected, token = self._paginate(request, context, vols)

        # TODO(geguileo): Once we support volume types set attributes
        entries = [
            types.Entry(volume=types.Volume(
                capacity_bytes=int(vol.size * constants.GB),
                id=vol.id,
                attributes={}))
            for vol in selected
        ]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return types.ListResp(**fields)

    @common.debuggable
    @common.logrpc
    def GetCapacity(self, request, context):
        self._validate_capabilities(request.volume_capabilities, context)
        # TODO(geguileo): Take into account over provisioning values
        stats = self.backend.stats(refresh=True)
        if 'pools' in stats:
            stats = stats['pools'][0]
        free = stats['free_capacity_gb']

        # TODO(geguileo): Confirm available capacity is in bytes
        return types.CapacityResp(available_capacity=int(free * constants.GB))

    @common.debuggable
    @common.logrpc
    def ControllerGetCapabilities(self, request, context):
        rpcs = (types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                types.CtrlCapabilityType.LIST_VOLUMES,
                # types.CtrlCapabilityType.CREATE_DELETE_SNAPSHOTS,
                # types.CtrlCapabilityType.LIST_SNAPSHOTS,
                types.CtrlCapabilityType.GET_CAPACITY)

        capabilities = [types.CtrlCapability(rpc=types.CtrlRPC(type=rpc))
                        for rpc in rpcs]

        return types.CtrlCapabilityResp(capabilities=capabilities)

    @common.debuggable
    @common.logrpc
    def CreateSnapshot(self, request, context):
        vol = self._get_vol(request.source_volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)
        snap = self._get_snap(snapshot_name=request.name,
                              volume_id=request.source_volume_id)
        # If we have multiple references there's something wrong, either the
        # same DB used for multiple purposes and there is a collision name, or
        # there's been a race condition, so we cannot be idempotent, create a
        # new volume.
        if isinstance(snap, cinderlib.Snapshot):
            print('Snapshot %s exists with id %s' % (request.name, vol.id))
        else:
            snap = vol.create_snapshot(name=request.name)
        snapshot = type.Snapshot(
            size_bytes=int(snap.volume_size * constants.GB),
            id=snap.id,
            source_volume_id=vol.id,
            created_at=common.date_to_nano(snap.created_at),
            status=types.SnapStatus(types.SnapshotStatusType.READY))
        return types.CreateSnapResp(snapshot=snapshot)

    @common.debuggable
    @common.logrpc
    def DeleteSnapshot(self, request, context):
        snap = self._get_snap(request.snapshot_id)
        if not snap:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Snapshot %s does not exist' % request.snapshot_id)
        snap.delete()
        return self.DELETE_SNAP_RESP

    @common.debuggable
    @common.logrpc
    def ListSnapshots(self, request, context):
        snaps = self._get_snap()
        selected, token = self._paginate(request, context, snaps)

        # TODO(geguileo): Once we support volume types set attributes
        entries = [types.SnapEntry(snapshot=types.Snapshot(
            size_bytes=int(snap.volume_size * constants.GB),
            id=snap.id,
            source_volume_id=snap.volume_id,
            created_at=common.date_to_nano(snap.created_at),
            status=types.SnapStatus(types.SnapshotStatusType.READY)))
            for snap in selected
        ]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return types.ListSnapResp(**fields)


class Node(csi.NodeServicer, Identity):
    STAGE_RESP = types.StageResp()
    UNSTAGE_RESP = types.UnstageResp()
    NODE_PUBLISH_RESP = types.NodePublishResp()
    NODE_UNPUBLISH_RESP = types.NodeUnpublishResp()

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        if persistence_config:
            ember_config['fail_on_missing_backend'] = False
            plugin_name = ember_config.pop('plugin_name', None)
            cinderlib.setup(persistence_config=persistence_config,
                            **ember_config)
            Identity.__init__(self, server, ember_config, plugin_name)

        node_id = node_id or socket.getfqdn()
        self.node_id = types.IdResp(node_id=node_id)
        self.node_info = NodeInfo.set(node_id, storage_nw_ip)
        csi.add_NodeServicer_to_server(self, server)

    def _get_split_file(self, filename):
        with open(filename) as f:
            result = [line.split() for line in f.read().split('\n') if line]
        return result

    def _get_mountinfo(self):
        return self._get_split_file('/proc/self/mountinfo')

    def _vol_private_location(self, volume_id):
        private_bind = os.path.join(os.getcwd(), volume_id)
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

    def _check_path(self, request, context, is_staging):
        is_block = request.volume_capability.HasField('block')
        attr_name = 'staging_target_path' if is_staging else 'target_path'
        path = getattr(request, attr_name)
        try:
            st_mode = os.stat(path).st_mode
        except OSError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Invalid %s path: %s' % (attr_name, exc))

        if ((is_block and stat.S_ISBLK(st_mode) or stat.S_ISREG(st_mode)) or
                (not is_block and stat.S_ISDIR(st_mode))):
            return path, is_block

        context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                      'Invalid existing %s' % attr_name)

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
        target, is_block = self._check_path(request, context, is_staging=True)

        device, private_bind = self._get_vol_device(vol.id)
        if not device:
            # For now we don't really require the publish_info, since we share
            # the persistence storage, but if we would need to deserialize it
            # with json.loads from key 'connection_info'
            conn = vol.connections[0]
            # Some slow systems may take a while to detect the multipath so we
            # retry the attach.  Since we don't disconnect this will go fast
            # through the login phase.
            for i in range(constants.MULTIPATH_FIND_RETRIES):
                conn.attach()
                if not conn.use_multipath or conn.path.startswith('/dev/dm'):
                    break
                sys.stdout.write('Retrying to get a multipath\n')
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
                self.sudo('mount', '--bind', private_bind, target)
        else:
            if not self._check_mount_exists(request.volume_capability,
                                            private_bind, target, context):
                fs_type = (request.volume_capability.mount.fs_type or
                           config.DEFAULT_MOUNT_FS)
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
                self.sudo('umount', request.staging_target_path,
                          retries=4)
            if count > 0:
                self.sudo('umount', private_bind, retries=4)
            os.remove(private_bind)

            conn = vol.connections[0]
            conn.detach()

        return self.UNSTAGE_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'staging_target_path', 'target_path',
                    'volume_capability')
    @common.Worker.unique
    def NodePublishVolume(self, request, context):
        self._validate_capabilities([request.volume_capability], context)
        staging_target, is_block = self._check_path(request, context,
                                                    is_staging=True)

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

        target, is_block = self._check_path(request, context, is_staging=False)

        # TODO(geguileo): Add support for modes, etc.

        # Check if it's already published
        device = self._get_device(target)
        volume_device, private_bind = self._get_vol_device(request.volume_id)
        if device in (volume_device, staging_target, private_bind):
            return self.NODE_PUBLISH_RESP

        # TODO(geguileo): Check how many are mounted and fail if > 0

        # If not published bind it
        self.sudo('mount', '--bind', staging_target, target)
        return self.NODE_PUBLISH_RESP

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'target_path')
    @common.Worker.unique
    def NodeUnpublishVolume(self, request, context):
        device = self._get_device(request.target_path)
        if device:
            self.sudo('umount', request.target_path, retries=4)
        return self.NODE_UNPUBLISH_RESP

    @common.debuggable
    @common.logrpc
    def NodeGetId(self, request, context):
        return self.node_id

    @common.debuggable
    @common.logrpc
    def NodeGetCapabilities(self, request, context):
        rpc = types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME
        capabilities = [types.NodeCapability(rpc=types.NodeRPC(type=rpc))]
        return types.NodeCapabilityResp(capabilities=capabilities)


class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            ember_config=ember_config)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)
