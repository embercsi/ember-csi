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

from ember_csi import base
from ember_csi import common
from ember_csi import config
from ember_csi import constants
from ember_csi.v0_3_0 import csi_pb2_grpc as csi
from ember_csi.v0_3_0 import csi_types as types


CONF = config.CONF


class Controller(base.TopologyBase, base.SnapshotBase, base.ControllerBase):
    CSI = csi
    TYPES = types
    DELETE_SNAP_RESP = types.DeleteSnapResp()
    CTRL_CAPABILITIES = [types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                         types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                         types.CtrlCapabilityType.LIST_VOLUMES,
                         types.CtrlCapabilityType.GET_CAPACITY,
                         types.CtrlCapabilityType.CREATE_DELETE_SNAPSHOT,
                         types.CtrlCapabilityType.LIST_SNAPSHOTS]

    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, **kwargs):
        self._init_topology(types.ServiceType.ACCESSIBILITY_CONSTRAINTS)
        super(Controller, self).__init__(server, persistence_config,
                                         backend_config, ember_config,
                                         **kwargs)

    # CreateVolume implemented on base Controller class which requires
    # _validate_requirements, _create_volume, and _convert_volume_type
    # methods.
    def _validate_requirements(self, request, context):
        super(Controller, self)._validate_requirements(request, context)
        self._validate_accessibility(request, context)

    def _create_volume(self, name, vol_size, request, context, **params):
        if not request.HasField('volume_content_source'):
            return super(Controller, self)._create_volume(name, vol_size,
                                                          request, context,
                                                          **params)
        # Check size
        self._fail_if_disabled(context, constants.SNAPSHOT_FEATURE)
        source = request.volume_content_source
        vol = self._create_from_snap(source.snapshot.snapshot_id, vol_size,
                                     request.name, context, **params)
        return vol

    def _convert_volume_type(self, vol):
        specs = vol.volume_type.extra_specs if vol.volume_type_id else None
        parameters = dict(capacity_bytes=int(vol.size * constants.GB),
                          id=vol.id,
                          attributes=specs)

        # If we pass the request we could do
        # if not request.HasField('volume_content_source'):
        #    parameters['content_source'] = request.content_source
        if vol.snapshot_id:
            parameters['content_source'] = types.VolumeContentSource(
                snapshot=types.SnapshotSource(snapshot_id=vol.snapshot_id))

        # accessible_topology should only be returned if we reported
        # ACCESSIBILITY_CONSTRAINTS capability.
        if self.GRPC_TOPOLOGIES:
            parameters['accessible_topology'] = self.GRPC_TOPOLOGIES

        return types.Volume(**parameters)

    # DeleteVolume implemented on base Controller class

    # ControllerPublishVolume implemented on base Controller class.

    # ControllerUnpublishVolume implemented on base Controller class.
    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_capabilities')
    def ValidateVolumeCapabilities(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)
        message = self._assert_req_cap_matches_vol(vol, request)
        if message:
            return types.ValidateResp(message=message)

        if request.volume_attributes:
            for k, v in request.parameters.items():
                v2 = request.volume_context.get(k)
                if v != v2:
                    message = 'Parameter %s does not match' % k
                    break

        for topology in request.accessible_topology:
            if not self._topology_is_accessible(topology, context):
                message = 'Not accessible from topology %s' % topology
                break

        return types.ValidateResp(supported=not bool(message), message=message)

    # ListVolumes implemented on base Controller class
    # Requires _convert_volume_type method.

    # GetCapacity implemented on base Controller class which requires
    # _validate_requirements

    def _convert_snapshot_type(self, snap):
        created_at = int(common.date_to_nano(snap.created_at))
        snapshot = types.Snapshot(
            id=snap.id,
            source_volume_id=snap.volume_id,
            created_at=created_at,
            status=types.SnapStatus(type=types.SnapStatusType.READY))
        return snapshot


class Node(base.NodeBase):
    CSI = csi
    TYPES = types
    NODE_CAPABILITIES = (types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME,)
    NODE_TOPOLOGY = None

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        self.node_id = types.IdResp(node_id=node_id)
        topo_capab = self.TYPES.ServiceType.ACCESSIBILITY_CONSTRAINTS
        if CONF.NODE_TOPOLOGY:
            if topo_capab not in self.PLUGIN_CAPABILITIES:
                self.PLUGIN_CAPABILITIES.append(topo_capab)
            self.NODE_TOPOLOGY = self.TYPES.Topology(
                segments=CONF.NODE_TOPOLOGY)
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

    @common.debuggable
    @common.logrpc
    def NodeGetId(self, request, context):
        return self.node_id

    # NodeGetCapabilities implemented on base Controller class using
    # NODE_CAPABILITIES attribute.

    @common.debuggable
    @common.logrpc
    def NodeGetInfo(self, request, context):
        return self.node_info_resp

    def _get_pod_uid(self, request):
        return request.volume_attributes.get('csi.storage.k8s.io/pod.uid')


class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            ember_config=ember_config)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)
