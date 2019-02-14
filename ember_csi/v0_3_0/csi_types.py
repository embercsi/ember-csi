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

from google.protobuf import wrappers_pb2 as wrappers

from ember_csi import common
from ember_csi.v0_3_0 import csi_pb2

Bool = wrappers.BoolValue

InfoResp = csi_pb2.GetPluginInfoResponse
NodeInfoResp = csi_pb2.NodeGetInfoResponse

Capability = csi_pb2.PluginCapability
Service = Capability.Service
ServiceType = common.EnumWrapper(Service.Type)
CtrlCapability = csi_pb2.ControllerServiceCapability
CtrlRPC = CtrlCapability.RPC
CtrlCapabilityType = common.EnumWrapper(CtrlRPC.Type)
CtrlCapabilityResp = csi_pb2.ControllerGetCapabilitiesResponse

NodeCapability = csi_pb2.NodeServiceCapability
NodeRPC = NodeCapability.RPC
NodeCapabilityType = common.EnumWrapper(NodeRPC.Type)
NodeCapabilityResp = csi_pb2.NodeGetCapabilitiesResponse

ListResp = csi_pb2.ListVolumesResponse
Entry = ListResp.Entry
ValidateResp = csi_pb2.ValidateVolumeCapabilitiesResponse

CtrlPublishResp = csi_pb2.ControllerPublishVolumeResponse

CapabilitiesResp = csi_pb2.GetPluginCapabilitiesResponse
AccessModeType = common.EnumWrapper(csi_pb2.VolumeCapability.AccessMode.Mode)
UnpublishResp = csi_pb2.ControllerUnpublishVolumeResponse

StageResp = csi_pb2.NodeStageVolumeResponse
UnstageResp = csi_pb2.NodeUnstageVolumeResponse
NodePublishResp = csi_pb2.NodePublishVolumeResponse
NodeUnpublishResp = csi_pb2.NodeUnpublishVolumeResponse
IdResp = csi_pb2.NodeGetIdResponse
ProbeRespOK = csi_pb2.ProbeResponse(ready=Bool(value=True))
CapacityResp = csi_pb2.GetCapacityResponse
CreateResp = csi_pb2.CreateVolumeResponse
DeleteResp = csi_pb2.DeleteVolumeResponse
Volume = csi_pb2.Volume

Snapshot = csi_pb2.Snapshot
CreateSnapResp = csi_pb2.CreateSnapshotResponse
SnapStatus = csi_pb2.SnapshotStatus
SnapStatusType = common.EnumWrapper(SnapStatus.Type)
DeleteSnapResp = csi_pb2.DeleteSnapshotResponse
ListSnapResp = csi_pb2.ListSnapshotsResponse
SnapEntry = ListSnapResp.Entry

Topology = csi_pb2.Topology
