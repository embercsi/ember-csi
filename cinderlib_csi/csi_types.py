import csi_pb2


class EnumWrapper(object):
    def __init__(self, enum):
        self._enum = enum

    def __getattr__(self, name):
        try:
            return getattr(self._enum, name)
        except AttributeError:
            return self._enum.Value(name)

InfoResp = csi_pb2.GetPluginInfoResponse

Capability = csi_pb2.PluginCapability
Service = Capability.Service
ServiceType = EnumWrapper(Service.Type)
CtrlCapability = csi_pb2.ControllerServiceCapability
CtrlRPC = CtrlCapability.RPC
CtrlCapabilityType = EnumWrapper(CtrlRPC.Type)
CtrlCapabilityResp = csi_pb2.ControllerGetCapabilitiesResponse

NodeCapability = csi_pb2.NodeServiceCapability
NodeRPC = NodeCapability.RPC
NodeCapabilityType = EnumWrapper(NodeRPC.Type)
NodeCapabilityResp = csi_pb2.NodeGetCapabilitiesResponse

ListResp = csi_pb2.ListVolumesResponse
Entry = ListResp.Entry
ValidateResp = csi_pb2.ValidateVolumeCapabilitiesResponse

CtrlPublishResp = csi_pb2.ControllerPublishVolumeResponse

CapabilitiesResp = csi_pb2.GetPluginCapabilitiesResponse
AccessModeType = EnumWrapper(csi_pb2.VolumeCapability.AccessMode.Mode)
UnpublishResp = csi_pb2.ControllerUnpublishVolumeResponse

StageResp = csi_pb2.NodeStageVolumeResponse
UnstageResp = csi_pb2.NodeUnstageVolumeResponse
NodePublishResp = csi_pb2.NodePublishVolumeResponse
NodeUnpublishResp = csi_pb2.NodeUnpublishVolumeResponse
IdResp = csi_pb2.NodeGetIdResponse
ProbeResp = csi_pb2.ProbeResponse
CapacityResp = csi_pb2.GetCapacityResponse
CreateResp = csi_pb2.CreateVolumeResponse
DeleteResp = csi_pb2.DeleteVolumeResponse
Volume = csi_pb2.Volume

Snapshot = csi_pb2.Snapshot
CreateSnapResp = csi_pb2.CreateSnapshotResponse
SnapStatus = EnumWrapper(csi_pb2.SnapshotStatus)
SnapStatusType = EnumWrapper(SnapStatus.Type)
DeleteSnapResp = csi_pb2.DeleteSnapshotResponse
ListSnapResp = csi_pb2.ListSnapshotsResponse
SnapEntry = ListSnapResp.Entry


def CapabilitiesResponse(types):
    capabilities = [csi_pb2.PluginCapability(service=Service(type=type))
                    for type in types]
    return CapabilitiesResp(capabilities=capabilities)
