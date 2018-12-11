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
from builtins import int
import os
import stat
import sys

import cinderlib
from google.protobuf import timestamp_pb2
import grpc

from ember_csi import base
from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi.v1_0_0 import csi_pb2_grpc as csi
from ember_csi.v1_0_0 import csi_types as types


class Controller(base.ControllerBase):
    CSI = csi
    TYPES = types
    PROBE_RESP = types.ProbeResp(ready=types.Bool(value=True))
    DELETE_SNAP_RESP = types.DeleteSnapResp()
    CTRL_CAPABILITIES = (types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                         types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                         types.CtrlCapabilityType.LIST_VOLUMES,
                         types.CtrlCapabilityType.GET_CAPACITY,
                         types.CtrlCapabilityType.CREATE_DELETE_SNAPSHOT,
                         types.CtrlCapabilityType.LIST_SNAPSHOTS,
                         types.CtrlCapabilityType.CLONE_VOLUME,
                         # types.CtrlCapabilityType.PUBLISH_READONLY,
                         )
    TOPOLOGIES = None
    # These 3 attributes are defined in __init__ if we have topologies
    # TOPOLOGY_HIERA = None
    # TOPOLOGY_LEVELS = None
    # TOPOLOGY_LEVELS_SET = None

    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, **kwargs):
        topo_capab = self.TYPES.ServiceType.VOLUME_ACCESSIBILITY_CONSTRAINTS
        if config.TOPOLOGIES:
            self.TOPOLOGY_HIERA = []
            self.TOPOLOGIES = []
            self.TOPOLOGY_LEVELS = []
            if topo_capab not in self.PLUGIN_CAPABILITIES:
                self.PLUGIN_CAPABILITIES.append(topo_capab)

            for topology in config.TOPOLOGIES:

                topo = tuple((k.lower(), v) for k, v in topology.items())
                topology = self.TYPES.Topology(segments=topology)

                if len(topo) >= len(self.TOPOLOGY_LEVELS):
                    for k, v in topo[len(self.TOPOLOGY_LEVELS):]:
                        self.TOPOLOGY_LEVELS.append(k)

                replace = None
                for i, t in enumerate(self.TOPOLOGY_HIERA):
                    if t[:len(topo)] == topo:
                        sys.stderr.write('Warning: Ignoring topology %s. Is '
                                         'included in %s' % (t, topo))
                        replace = i
                        break
                    elif topo[:len(t)] == t:
                        sys.stderr.write('Warning: Ignoring topology %s. Is '
                                         'included in %s' % (topo, t))
                        break
                else:
                    self.TOPOLOGY_HIERA.append(topo)
                    self.TOPOLOGIES.append(topology)

                if replace is not None:
                    self.TOPOLOGY_HIERA[i] = topo
                    self.TOPOLOGIES[i] = topology

            sys.stdout.write("topology: %s" % self.TOPOLOGY_HIERA)
            self.TOPOLOGY_LEVELS_SET = set(self.TOPOLOGY_LEVELS)

        super(Controller, self).__init__(server, persistence_config,
                                         backend_config, ember_config,
                                         **kwargs)

    def _topology_is_accessible(self, topology, context):
        topo = []
        unused_domains = set(topology.keys())

        for domain in self.TOPOLOGY_LEVELS:
            if domain not in topology:
                break
            topo.append((domain, topology[domain]))
            unused_domains.remove(domain)

        # We used the domains in hierarchical order, if there is any known
        # domain in the request we haven't used, then there was one level that
        # was missing.
        if unused_domains.intersection(self.TOPOLOGY_LEVELS_SET):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Missing domain topology in request.')

        for t in self.TOPOLOGY_HIERA:
            if topo == t[:len(topo)]:
                return True
        return False

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

        to_check = requisite or preferred
        for topology in to_check:
            if self._topology_is_accessible(topology, context):
                return
        context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                      'None of the requested topologies are accessible.')

    def _validate_accessibility(self, request, context):
        if not self.TOPOLOGIES:
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

    def _get_snap(self, snapshot_id=None, always_list=False, **filters):
        res = self.persistence.get_snapshots(
            snapshot_id=snapshot_id, **filters)
        if (not always_list and
                (res and len(res) == 1 and (snapshot_id or filters))):
            return res[0]
        return res

    # CreateVolume implemented on base Controller class which requires
    # _validate_requirements, _create_volume, and _convert_volume_type
    # methods.
    def _validate_requirements(self, request, context):
        super(Controller, self)._validate_requirements(request, context)
        self._validate_accessibility(request, context)

    def _create_from_snap(self, snap_id, vol_size, name, context):
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
        vol = src_snap.create_volume(name=name)
        return vol

    def _create_from_vol(self, vol_id, vol_size, name, context):
        src_vol = self._get_vol(volume_id=vol_id)

        if not src_vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % vol_id)
        if src_vol.status not in ('available', 'in-use'):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          'Volume %s is not available' % vol_id)
        if src_vol.volume_size > vol_size:
            context.abort(grpc.StatusCode.OUT_OF_RANGE,
                          'Volume %s is bigger than requested volume' % vol_id)
        vol = src_vol.clone(name=name, size=vol_size)
        return vol

    def _create_volume(self, name, vol_size, request, context):
        if not request.HasField('volume_content_source'):
            return super(Controller, self)._create_volume(name, vol_size,
                                                          request, context)
        # Check size
        source = request.volume_content_source
        if source.HasField('snapshot'):
            vol = self._create_from_snap(source.snapshot.snapshot_id, vol_size,
                                         request.name, context)

        else:
            vol = self._create_from_vol(source.volume.volume_id, vol_size,
                                        request.name, context)
        return vol

    def _convert_volume_type(self, vol):
        specs = vol.volume_type.extra_specs if vol.volume_type_id else None
        parameters = dict(capacity_bytes=int(vol.size * constants.GB),
                          volume_id=vol.id,
                          volume_context=specs)

        # If we pass the request we could do
        # if not request.HasField('volume_content_source'):
        #    parameters['content_source'] = request.content_source
        if vol.source_volid:
            parameters['volume_content_source'] = types.VolumeContentSource(
                volume=types.VolumeSource(volume_id=vol.source_vol_id))

        elif vol.snapshot_id:
            parameters['volume_content_source'] = types.VolumeContentSource(
                snapshot=types.SnapshotSource(snapshot_id=vol.snapshot_id))

        # accessible_topology should only be returned if we reported
        # VOLUME_ACCESSIBILITY_CONSTRAINTS capability.
        if self.TOPOLOGIES:
            parameters['accessible_topology'] = self.TOPOLOGIES

        volume = types.Volume(**parameters)
        return types.CreateResp(volume=volume)

    # DeleteVolume implemented on base Controller class

    # ControllerPublishVolume implemented on base Controller class.
    # Requires _controller_publish_results method.
    def _controller_publish_results(self, connection_info):
        return types.CtrlPublishResp(publish_context=connection_info)

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_capabilities')
    def ValidateVolumeCapabilities(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

        message = self._validate_capabilities(request.volume_capabilities)
        if message:
            return types.ValidateResp(message=message)

        if request.parameters:
            for k, v in request.parameters.items():
                v2 = request.volume_context.get(k)
                if v != v2:
                    message = 'Parameter %s does not match' % k
                    return types.ValidateResp(message=message)

        confirmed = types.ValidateResp.Confirmed(
            volume_context=request.volume_context,
            volume_capabilities=request.volume_capabilities,
            parameters=request.parameters)
        return types.ValidateResp(confirmed=confirmed)

    # ListVolumes implemented on base Controller class
    # Requires _convert_volume_type method.

    # GetCapacity implemented on base Controller class which requires
    # _validate_requirements

    # ControllerGetCapabilities implemented on base Controller class using the
    # CTRL_CAPABILITIES attribute.
    def _convert_snapshot_type(self, snap):
        creation_time = timestamp_pb2.Timestamp()
        created_at = snap.created_at.replace(tzinfo=None)
        creation_time.FromDatetime(created_at)

        snapshot = types.Snapshot(
            size_bytes=int(snap.volume_size * constants.GB),
            snapshot_id=snap.id,
            source_volume_id=snap.volume_id,
            creation_time=creation_time,
            ready_to_use=True)
        return snapshot

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
            print('Snapshot %s exists with id %s' % (request.name, snap.id))
        else:
            vol = self._get_vol(request.source_volume_id)
            if not vol:
                context.abort(grpc.StatusCode.NOT_FOUND,
                              'Volume %s does not exist' % request.volume_id)
            snap = vol.create_snapshot(name=request.name)
        snapshot = self._convert_snapshot_type(snap)
        return types.CreateSnapResp(snapshot=snapshot)

    @common.debuggable
    @common.logrpc
    @common.require('snapshot_id')
    @common.Worker.unique('snapshot_id')
    def DeleteSnapshot(self, request, context):
        snap = self._get_snap(request.snapshot_id)
        if snap:
            snap.delete()
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

        entries = [types.SnapEntry(snapshot=self._convert_snapshot_type(snap))
                   for snap in selected]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return types.ListSnapResp(**fields)


class Node(base.NodeBase):
    CSI = csi
    TYPES = types
    NODE_CAPABILITIES = (types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME,
                         types.NodeCapabilityType.GET_VOLUME_STATS)
    NODE_TOPOLOGY = None

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        # TODO(geguileo): Report max_volumes_per_node based on driver
        topo_capab = self.TYPES.ServiceType.VOLUME_ACCESSIBILITY_CONSTRAINTS
        if config.NODE_TOPOLOGY:
            if topo_capab not in self.PLUGIN_CAPABILITIES:
                self.PLUGIN_CAPABILITIES.append(topo_capab)
            self.NODE_TOPOLOGY = self.TYPES.Topology(
                segments=config.NODE_TOPOLOGY)
        super(Node, self).__init__(server, persistence_config, ember_config,
                                   node_id, storage_nw_ip, **kwargs)
        params = dict(node_id=node_id)
        if self.NODE_TOPOLOGY:
            params['accessible_topology'] = self.NODE_TOPOLOGY
        self.node_info_resp = types.NodeInfoResp(**params)

    # NodeStageVolume implemented on base Controller class
    # NodeUnstageVolume implemented on base Controller class
    # NodePublishVolume implemented on base Controller class
    # NodeUnpublishVolume implemented on base Controller class

    # TODO(geguileo): Implement NodeGetVolumeStats
    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_path')
    @common.Worker.unique('volume_id')
    def NodeGetVolumeStats(self, request, context):
        path = request.volume_path
        try:
            st_mode = os.stat(path).st_mode
        except OSError:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Cannot access path %s' % path)

        device_for_path = self._get_device(path)
        device_for_vol, private_bind = self._get_vol_device(request.volume_id)

        if not device_for_vol or device_for_path != private_bind:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Path does not match with requested volume')

        if stat.S_ISDIR(st_mode):
            stats = os.statvfs(path)
            size = stats.f_frsize * stats.f_blocks
            available = stats.f_frsize * stats.f_bavail
            used = size - available

        else:  # is block
            size_name = os.path.join('/sys/class/block',
                                     os.path.basename(device_for_vol), 'size')
            with open(size_name) as f:
                blocks = int(f.read())
            size = 512 * blocks
            used = available = None

        return types.VolumeStatsResp(usage=[types.VolumeUsage(
            unit=types.UsageUnit.BYTES,
            total=size,
            used=used,
            available=available)])

    # NodeGetCapabilities implemented on base Controller class using
    # NODE_CAPABILITIES attribute.

    @common.debuggable
    @common.logrpc
    def NodeGetInfo(self, request, context):
        return self.node_info_resp


class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            ember_config=ember_config)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)
