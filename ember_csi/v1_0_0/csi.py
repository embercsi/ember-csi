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

from ember_csi import config
from ember_csi.v1_0_0 import csi_base as v1_base
from ember_csi.v1_0_0 import csi_pb2_grpc as csi
from ember_csi.v1_0_0 import csi_types as types


CONF = config.CONF


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
                         types.CtrlCapabilityType.PUBLISH_READONLY]


class Node(v1_base.Node):
    CSI = csi
    TYPES = types
    NODE_CAPABILITIES = (types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME,
                         types.NodeCapabilityType.GET_VOLUME_STATS)
    NODE_TOPOLOGY = None


class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 ember_config=None, node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            ember_config=ember_config)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)
