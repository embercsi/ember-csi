# Copyright (c) 2019, Red Hat, Inc.
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
from builtins import int
import os

import grpc
from oslo_log import log as logging

from ember_csi import config
from ember_csi import common
from ember_csi import constants
from ember_csi.v1_0_0 import csi_base as v1_base
from ember_csi.v1_1_0 import csi_pb2_grpc as csi
from ember_csi.v1_1_0 import csi_types as types


CONF = config.CONF
LOG = logging.getLogger(__name__)


def _add_expand_plugin_capabilities(grpc_capabilities, disabled_features):
    if constants.EXPAND_FEATURE in disabled_features:
        return

    if constants.EXPAND_ONLINE_FEATURE not in disabled_features:
        expansion_type = types.Expansion(type=types.ExpansionType.ONLINE)
    else:
        expansion_type = types.Expansion(type=types.ExpansionType.OFFLINE)

    plugin_capability = types.Capability(volume_expansion=expansion_type)

    # May have already been added by the other class (Node-Controller) if we
    # are running as both (All)
    if plugin_capability not in grpc_capabilities:
        grpc_capabilities.append(plugin_capability)


class Controller(v1_base.Controller):
    CSI = csi
    TYPES = types
    DELETE_SNAP_RESP = types.DeleteSnapResp()
    CTRL_CAPABILITIES = [types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                         types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                         types.CtrlCapabilityType.LIST_VOLUMES,
                         types.CtrlCapabilityType.GET_CAPACITY,
                         types.CtrlCapabilityType.CREATE_DELETE_SNAPSHOT,
                         types.CtrlCapabilityType.LIST_SNAPSHOTS,
                         types.CtrlCapabilityType.CLONE_VOLUME,
                         types.CtrlCapabilityType.PUBLISH_READONLY,
                         types.CtrlCapabilityType.EXPAND_VOLUME]

    def _disable_features(self, features):
        # Snapshot disabling is handled by SnapshotBase
        # Clone disabling is handled by vm-base.Controller
        # Expand is reported both as Controller, Node, and Plugin capabilities

        # Add expand plugin capabilities if not disabled
        _add_expand_plugin_capabilities(self.PLUGIN_GRPC_CAPABILITIES,
                                        self.disabled_features)
        # Expand is enabled by default.  Nothing to do if not disabled
        if constants.EXPAND_FEATURE not in features:
            return

        # Don't report the controller capability if disabled
        capab = self.TYPES.CtrlCapabilityType.EXPAND_VOLUME
        if capab in self.CTRL_CAPABILITIES:
            self.CTRL_CAPABILITIES.remove(capab)

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'capacity_range')
    @common.Worker.unique('volume_id')
    def ControllerExpandVolume(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)

        # Validate and get requested sizes
        vol_size, min_size, max_size = self._calculate_size(request, context)
        if vol.size > vol_size:
            context.abort(grpc.StatusCode.OUT_OF_RANGE,
                          'Volume cannot shrink from %s to %s' % (vol.size,
                                                                  vol_size))

        # We may be receiving a second call after the first one failed.
        # No need to save, it will be saved when we call extend and succeed.
        if vol.status == 'error':
            vol._ovo.status = vol.previous_status
        used = vol.status == 'in-use'

        # Fail if online expansion is disabled
        if used and constants.EXPAND_ONLINE_FEATURE in self.disabled_features:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Online expansion is disabled')

        if min_size <= vol.size <= max_size:
            LOG.debug('No expansion necessary in the backend, volume already '
                      'has %sGB size', vol.size)
        else:
            LOG.debug('Expanding volume %s from %s to %s',
                      vol.id, vol.size, vol_size)
            vol.extend(vol_size)

        # Return size and tell CO we need a call node expansion to finish
        # if it's currently attached (will be called now), or if it's a mount
        # volume even if it's detached (it will be called after it is staged).
        node_expansion = bool(used or self._get_fs_type(vol))
        current_size = int(vol_size * constants.GB)
        return types.CtrlExpandResp(capacity_bytes=current_size,
                                    node_expansion_required=node_expansion)


class Node(v1_base.Node):
    CSI = csi
    TYPES = types
    NODE_CAPABILITIES = [types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME,
                         types.NodeCapabilityType.GET_VOLUME_STATS,
                         types.NodeCapabilityType.EXPAND_VOLUME]
    NODE_TOPOLOGY = None
    EXT_FS = ('ext2', 'ext3', 'ext4')

    def _disable_features(self, features):
        # Expand is reported both as Controller, Node, and Plugin capabilities

        # Add expand plugin capabilities if not disabled
        _add_expand_plugin_capabilities(self.PLUGIN_GRPC_CAPABILITIES,
                                        self.disabled_features)

        # Expand is enabled by default, so if we don't disable it as a whole
        # or disable online we have nothing to do here.
        if not (constants.EXPAND_FEATURE in features
                or constants.EXPAND_ONLINE_FEATURE in features):
            return

        # Disabled expand or just online means that the node has nothing to do
        capab = self.TYPES.NodeCapabilityType.EXPAND_VOLUME
        if capab in self.NODE_CAPABILITIES:
            self.NODE_CAPABILITIES.remove(capab)

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_path')
    @common.Worker.unique('volume_id')
    def NodeExpandVolume(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)
        vol_size = vol.size
        # If the size is given, check that it makes sense
        if request.HasField('capacity_range'):
            v_size, min_size, max_size = self._calculate_size(request, context)
            if not (min_size <= vol_size <= max_size):
                context.abort(grpc.StatusCode.OUT_OF_RANGE,
                              "New size requested (%s) doesn't match "
                              "controller resized volume (%s)" %
                              (v_size, vol.size))

        device, private_bind = self._get_vol_device(request.volume_id)

        # Volume is not mounted, nothing to do (could be a second call)
        if not device:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          'Volume is not mounted, cannot resize')

        # TODO: Check it's the right path

        # The extend call will return the size in bytes, like we want
        current_size = vol.connections[0].extend()

        # Extend filesystem if necessary
        self._resize_fs(context, vol, private_bind)

        return types.NodeExpandResp(capacity_bytes=current_size)

    def _resize_fs(self, context, vol, private_bind):
        fs_type = self._get_fs_type(vol)
        if not fs_type:
            return

        # We always do mounted resizing, for available and in-use volumes, so
        # we don't have to differentiate between btrfs and xfs, and ext fs.
        mounts = self._get_mount(private_bind)
        target = mounts[0][1]

        # All volumes are mounted on the stage directory, make sure we have the
        # right path
        if os.path.basename(target) != self.STAGED_NAME:
            LOG.warning("target didn't have the /stage ending")
            target = os.path.join(target, self.STAGED_NAME)

        # Our volumes don't have partitions, so we don't need to extend them.
        # For ext3 we need to have the resize_inode feature enabled to be able
        # to do mounted resize, which is enabled by default in /etc/mkefs.conf
        if fs_type in self.EXT_FS:
            command = ('resize2fs', '-f', '-F', private_bind)

        elif fs_type == 'btrfs':
            command = ('btrfs', 'filesystem', 'resize', 'max', target)

        elif fs_type == 'xfs':
            command = ('xfs_growfs', '-d', target)

        else:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "Don't know how to extend %s filesystem")

        self.sudo(*command)


class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            ember_config=ember_config)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)
