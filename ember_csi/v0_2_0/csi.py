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
import grpc

from ember_csi import base
from ember_csi import common
from ember_csi import constants
from ember_csi.v0_2_0 import csi_pb2_grpc as csi
from ember_csi.v0_2_0 import csi_types as types


class Controller(base.ControllerBase):
    CSI = csi
    TYPES = types
    CTRL_CAPABILITIES = [types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                         types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                         types.CtrlCapabilityType.LIST_VOLUMES,
                         types.CtrlCapabilityType.GET_CAPACITY]

    # CreateVolume implemented on base Controller class.
    # Requires _convert_volume_type method.
    def _convert_volume_type(self, vol):
        specs = vol.volume_type.extra_specs if vol.volume_type_id else None
        return types.Volume(capacity_bytes=int(vol.size * constants.GB),
                            id=vol.id,
                            attributes=specs)

    # DeleteVolume implemented on base Controller class

    # ControllerPublishVolume implemented on base Controller class.

    @common.debuggable
    @common.logrpc
    @common.require('volume_id', 'volume_capabilities')
    def ValidateVolumeCapabilities(self, request, context):
        vol = self._get_vol(request.volume_id, context=context)
        message = self._assert_req_cap_matches_vol(vol, request)
        # TODO(geguileo): Add support for attributes via volume types
        if not message and request.volume_attributes:
            message = "Parameters don't match"

        return types.ValidateResp(supported=not bool(message), message=message)

    # ListVolumes implemented on base Controller class
    # Requires _convert_volume_type method.

    # GetCapacity implemented on base Controller class which requires
    # _validate_requirements

    # ControllerGetCapabilities implemented on base Controller class using the
    # CAPABILITIES attribute.


class Node(base.NodeBase):
    CSI = csi
    TYPES = types
    NODE_CAPABILITIES = (types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME,)

    def __init__(self, server, persistence_config=None, ember_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        self.node_id = types.IdResp(node_id=node_id)
        super(Node, self).__init__(server, persistence_config, ember_config,
                                   node_id, storage_nw_ip, **kwargs)

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
