# Supports CSI v0.2.0
# TODO(geguileo): Check that all parameters are present on received RPC calls
from concurrent import futures
from datetime import datetime
import functools
import itertools
import json
import os
import socket
import time

from eventlet import tpool
import grpc
import cinderlib
from cinderlib import persistence
from os_brick.initiator import connector as brick_connector
from oslo_concurrency import processutils as putils
import pkg_resources
import pytz

import csi_pb2_grpc as csi
import csi_types as types


NAME = 'com.redhat.cinderlib-csi'
VENDOR_VERSION = '0.0.1'

DEFAULT_ENDPOINT = '[::]:50051'
DEFAULT_SIZE = 1.0
DEFAULT_PERSISTENCE_CFG = {'storage': 'db',
                           'connection': 'sqlite:///db.sqlite'}
DEFAULT_CINDERLIB_CFG = {'project_id': NAME, 'user_id': NAME,
                         'root_helper': 'sudo'}
REFRESH_TIME = 1

GB = float(1024 ** 3)
ONE_DAY_IN_SECONDS = 60 * 60 * 24
CINDER_VERSION = pkg_resources.get_distribution('cinder').version
NANOSECONDS = 10 ** 9
EPOCH = datetime.utcfromtimestamp(0).replace(tzinfo=pytz.UTC)


def date_to_nano(date):
    # Don't use str or six.text_type, as they truncate
    return repr((date - EPOCH).total_seconds() * NANOSECONDS)


def nano_to_date(nanoseconds):
    date = datetime.utcfromtimestamp(float(nanoseconds)/NANOSECONDS)
    return date.replace(tzinfo=pytz.UTC)


class NodeInfo(object):
    __slots__ = ('id', 'connector_dict')

    def __init__(self, node_id, connector_dict):
        self.id = node_id
        self.connector_dict = connector_dict

    @classmethod
    def get(cls, node_id):
        kv = cinderlib.Backend.persistence.get_key_values(node_id)
        # TODO(geguileo): Fail if info is not there
        return cls(node_id, json.loads(kv[0].value))

    @classmethod
    def set(self, node_id, storage_nw_ip):
        if not storage_nw_ip:
            storage_nw_ip = socket.gethostbyname(socket.gethostname())

        # For now just set multipathing and not enforcing it
        connector_dict = brick_connector.get_connector_properties(
            'sudo', storage_nw_ip, True, False)
        kv = cinderlib.KeyValue(node_id, json.dumps(connector_dict))
        cinderlib.Backend.persistence.set_key_value(kv)
        return NodeInfo(node_id, connector_dict)


class Identity(csi.IdentityServicer):
    backend = None
    PROBE_RESP = types.ProbeResp()
    CAPABILITIES = types.CapabilitiesResponse(
        [types.ServiceType.CONTROLLER_SERVICE])
    manifest = None

    def __init__(self, server):
        if self.manifest is not None:
            return

        manifest = {
            'cinderlib-version': cinderlib.__version__,
            'cinder-version': CINDER_VERSION,
        }
        if self.persistence:
            manifest['persistence'] = type(self.persistence).__name__

        if self.backend:
            manifest['cinder-driver-version'] = self.backend.get_version()
            manifest['cinder-driver'] = type(self.backend.driver).__name__
            manifest['cinder-driver-supported'] = str(self.backend.supported)

        self.INFO = types.InfoResp(name=NAME,
                                   vendor_version=VENDOR_VERSION,
                                   manifest=manifest)

        csi.add_IdentityServicer_to_server(self, server)
        self.manifest = manifest

    def GetPluginInfo(self, request, context):
        return self.INFO

    def GetPluginCapabilities(self, request, context):
        return self.CAPABILITIES

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
        res = self.persistence.get_volumes(
            volume_id=volume_id, backend_name=self.backend.id, **filters)
        if res and len(res) == 1 and (volume_id or filters):
            return res[0]
        return res

    def sudo(self, *cmd):
        putils.execute(*cmd, run_as_root=True, root_helper='sudo')


class Controller(csi.ControllerServicer, Identity):
    # NOTE(geguileo): For now let's only support single reader/writer modes
    SUPPORTED_ACCESS = (types.AccessModeType.SINGLE_NODE_WRITER,
                        types.AccessModeType.SINGLE_NODE_READER_ONLY)
    CTRL_UNPUBLISH_RESP = types.UnpublishResp()
    DELETE_RESP = types.DeleteResp()
    DELETE_SNAP_RESP = types.DeleteSnapResp()

    def __init__(self, server, persistence_config, backend_config,
                 cinderlib_config=None, default_size=DEFAULT_SIZE, **kwargs):
        self.default_size = default_size
        cinderlib.setup(persistence_config=persistence_config,
                        **cinderlib_config)
        self.backend = cinderlib.Backend(**backend_config)
        self.persistence = self.backend.persistence
        Identity.__init__(self, server)
        csi.add_ControllerServicer_to_server(self, server)

    def _get_size(self, what, request, default):
        vol_size = getattr(request.capacity_range, what + '_bytes', None)
        if vol_size:
            return vol_size / GB
        return default

    def _wait(self, vol, states, delete_on_error=False):
        # TODO(geguileo): Introduce timeout and probably cleanup mechanism
        status = vol.status
        while status not in states:
            if 'error' in vol.status:
                if delete_on_error:
                    vol.delete()
                return False
            time.sleep(REFRESH_TIME)
            vol = self._get_vol(vol.id)
            status = vol.status if vol else 'deleted'
        return True

    def _get_vol_node(self, request, context):
        node = NodeInfo.get(request.node_id)
        if not node:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Node %s does not exist' % request.node_id)

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

    def _unsupported_mode(self, capability):
        return capability.access_mode.mode not in self.SUPPORTED_ACCESS

    def _calculate_size(self, request, context):
        # Must be idempotent
        min_size = self._get_size('required', request, self.default_size)
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

    def _validate_capabilities(self, capabilities, vol=None):
        for cap in capabilities:
            # TODO(geguileo): Find out what is the right status code
            if not cap.HasField('block'):
                return 'Driver only supports block types'

            # TODO(geguileo): Find out what is the right status code
            if self._unsupported_mode(cap):
                return 'Unsupported access mode'

        return ''

    def CreateVolume(self, request, context):
        vol_size, min_size, max_size = self._calculate_size(request, context)

        msg = self._validate_capabilities(request.volume_capabilities)
        if msg:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)

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

        volume = types.Volume(capacity_bytes=int(vol.size * GB),
                              id=vol.id,
                              attributes=request.parameters)
        return types.CreateResp(volume=volume)

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

    def ControllerPublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)

        # The volume is already attached
        if vol.status == 'in-use':
            for conn in vol.connections:
                # TODO(geguileo): Change when we enable multi-attach
                if conn.instance_uuid != request.node_id:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                                  'Volume published to another node')

            # TODO(geguileo): Check capabilities and readonly compatibility
            #                 and raise ALREADY_EXISTS if not compatible
            conn = vol.connections[0]
        else:
            conn = vol.connect(node.connector_dict, instance_uuid=node.id)
        publish_info = {'connection_info': json.dumps(conn.connection_info)}
        return types.CtrlPublishResp(publish_info=publish_info)

    def ControllerUnpublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)

        # TODO(geguileo): With multi-attach use request.node_id to compare with
        # connection.instance_id
        if vol.status == 'in-use':
            vol.connections[0].disconnect()
        return self.CTRL_UNPUBLISH_RESP

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
                marker = nano_to_date(request.starting_token)
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
            token = date_to_nano(resources[end - 1].created_at)
        else:
            token = None
        return selected_resources, token

    def ListVolumes(self, request, context):
        vols = self._get_vol()
        selected, token = self._paginate(request, context, vols)

        # TODO(geguileo): Once we support volume types set attributes
        entries = [
            types.Entry(volume=types.Volume(capacity_bytes=int(vol.size * GB),
                                            id=vol.id,
                                            attributes={}))
            for vol in selected
        ]
        fields = {'entries': entries}
        if token:
            fields['next_token'] = token
        return types.ListResp(**fields)

    def GetCapacity(self, request, context):
        msg = self._validate_capabilities(request.volume_capabilities)
        if msg:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)
        # TODO(geguileo): Take into account over provisioning values
        stats = self.backend.stats(refresh=True)
        if 'pools' in stats:
            stats = stats['pools'][0]
        free = stats['free_capacity_gb']

        # TODO(geguileo): Confirm available capacity is in bytes
        return types.CapacityResp(available_capacity=int(free * GB))

    def ControllerGetCapabilities(self, request, context):
        rpcs = (types.CtrlCapabilityType.CREATE_DELETE_VOLUME,
                types.CtrlCapabilityType.PUBLISH_UNPUBLISH_VOLUME,
                types.CtrlCapabilityType.LIST_VOLUMES,
                types.CtrlCapabilityType.CREATE_DELETE_SNAPSHOTS,
                types.CtrlCapabilityType.LIST_SNAPSHOTS,
                types.CtrlCapabilityType.GET_CAPACITY)

        capabilities = [types.CtrlCapability(rpc=types.CtrlRPC(type=rpc))
                        for rpc in rpcs]

        return types.CtrlCapabilityResp(capabilities=capabilities)

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
            print('Volume %s exists with id %s' % (request.name, vol.id))
        else:
            snap = vol.create_snapshot(name=request.name)
        snapshot = type.Snapshot(
            size_bytes=int(snap.volume_size * GB),
            id=snap.id,
            source_volume_id=vol.id,
            created_at=date_to_nano(snap.created_at),
            status=types.SnapStatus(types.SnapshotStatusType.READY))
        return types.CreateSnapResp(snapshot=snapshot)

    def DeleteSnapshot(self, request, context):
        snap = self._get_snap(request.snapshot_id)
        if not snap:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Snapshot %s does not exist' % request.snapshot_id)
        snap.delete()
        return self.DELETE_SNAP_RESP

    def ListSnapshots(self, request, context):
        snaps = self._get_snap()
        selected, token = self._paginate(request, context, snaps)

        # TODO(geguileo): Once we support volume types set attributes
        entries = [types.SnapEntry(snapshot=types.Snapshot(
            size_bytes=int(snap.volume_size * GB),
            id=snap.id,
            source_volume_id=snap.volume_id,
            created_at=date_to_nano(snap.created_at),
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

    def __init__(self, server, persistence_config=None, node_id=None,
                 storage_nw_ip=None, **kwargs):
        if persistence_config:
            self.persistence = persistence.setup(persistence_config)
            # TODO(geguileo): Make Node only service work, which may require
            # modifications to cinderlib or faking the Backend object, since
            # all objects set the backend field on initialization.
            # cinderlib.objects.Object.setup(self.persistence, ...)

        node_id = node_id or socket.getfqdn()
        self.node_id = types.IdResp(node_id=node_id)
        self.node_info = NodeInfo.set(node_id, storage_nw_ip)
        Identity.__init__(self, server)
        csi.add_NodeServicer_to_server(self, server)

    def _get_mountinfo(self):
        with open('/proc/self/mountinfo') as f:
            mountinfo = [line.split() for line in f.read().split('\n') if line]
        return mountinfo

    def _vol_private_location(self, volume_id):
        private_bind = os.path.join(os.getcwd(), volume_id)
        return private_bind

    def _get_device(self, path):
        for line in self._get_mountinfo():
            if line[4] == path:
                return line[3]
        return None

    def _get_vol_device(self, volume_id):
        private_bind = self._vol_private_location(volume_id)
        device = self._get_device(private_bind)
        return device, private_bind

    def NodeStageVolume(self, request, context):
        vol = self._get_vol(request.volume_id)
        if not vol:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Volume %s does not exist' % request.volume_id)

        # TODO(geguileo): Check capabilities
        # TODO(geguileo): Check that the provided staging_target_path is an
        # existing file for block or directory for filesystems
        device, private_bind = self._get_vol_device(vol.id)
        if not device:
            # For now we don't really require the publish_info, since we share
            # the persistence storage, but if we would need to deserialize it
            # with json.loads from key 'connection_info'
            conn = vol.connections[0]
            conn.attach()
            # Create the private bind file
            open(private_bind, 'a').close()
            # TODO(geguileo): make path for private binds configurable
            self.sudo('mount', '--bind', conn.path, private_bind)

        # If CO did something wrong and called us twice avoid multiple binds
        device = self._get_device(request.staging_target_path)
        if not device:
            # TODO(geguileo): Add support for NFS/QCOW2
            self.sudo('mount', '--bind', private_bind,
                      request.staging_target_path)
        return self.STAGE_RESP

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

            # If the volume is still in use we cannot unstage (one use is for
            # our private volume reference and the other for staging path
            if count > 2:
                context.abort(grpc.StatusCode.ABORTED,
                              'Operation pending for volume')

            conn = vol.connections[0]
            if count == 2:
                self.sudo('umount', request.staging_target_path)
            conn.detach()
            if count > 0:
                self.sudo('umount', private_bind)
            os.remove(private_bind)
        return self.UNSTAGE_RESP

    def NodePublishVolume(self, request, context):

        # TODO(geguileo): Check if staging_target_path is passed and exists
        # TODO(geguileo): Add support for modes, etc.
        # Check if it's already published
        device = self._get_device(request.target_path)
        volume_device, private_bind = self._get_vol_device(request.volume_id)
        if device in (volume_device, request.staging_target_path):
            return self.NODE_PUBLISH_RESP

        # TODO(geguileo): Check how many are mounted and fail if > 0

        # If not published bind it
        self.sudo('mount', '--bind', request.staging_target_path,
                  request.target_path)
        return self.NODE_PUBLISH_RESP

    def NodeUnpublishVolume(self, request, context):
        device = self._get_device(request.target_path)
        if device:
            self.sudo('umount', request.target_path)
        return self.NODE_UNPUBLISH_RESP

    def NodeGetId(self, request, context):
        return self.node_id

    def NodeGetCapabilities(self, request, context):
        rpc = types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME
        capabilities = [types.NodeCapability(rpc=types.NodeRPC(type=rpc))]
        return types.NodeCapabilityResp(capabilities=capabilities)


# Inheritance order is important, as we only want to run Controller.__init__
class All(Controller, Node):
    def __init__(self, server, persistence_config, backend_config,
                 cinderlib_config=None, default_size=DEFAULT_SIZE,
                 node_id=None, storage_nw_ip=None):
        Controller.__init__(self, server,
                            persistence_config=persistence_config,
                            backend_config=backend_config,
                            cinderlib_config=cinderlib_config,
                            default_size=default_size)
        Node.__init__(self, server, node_id=node_id,
                      storage_nw_ip=storage_nw_ip)


class ServerProxy(tpool.Proxy):
    @staticmethod
    def _my_doit(method, *args, **kwargs):
        # cygrpc.Server methods don't acept proxied completion_queue
        unproxied_args = [arg._obj if isinstance(arg, tpool.Proxy) else arg
                          for arg in args]
        unproxied_kwargs = {k: v._obj if isinstance(v, tpool.Proxy) else v
                            for k, v in kwargs.items()}
        return method(*unproxied_args, **unproxied_kwargs)

    def __getattr__(self, attr_name):
        f = super(ServerProxy, self).__getattr__(attr_name)
        if hasattr(f, '__call__'):
            f = functools.partial(self._my_doit, f)
        return f

    def __call__(self, *args, **kwargs):
        return self._my_doit(super(ServerProxy, self).__call__,
                             *args, **kwargs)


def _load_json_config(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default

    try:
        return json.loads(value)
    except Exception:
        print('Invalid JSON data for %s' % name)
        exit(1)


def main():
    # CSI_ENDPOINT should accept multiple formats 0.0.0.0:5000, unix:foo.sock
    endpoint = os.environ.get('CSI_ENDPOINT', DEFAULT_ENDPOINT)
    mode = os.environ.get('CSI_MODE') or 'all'
    if mode not in ('controller', 'node', 'all'):
        print('Invalid mode value (%s)' % mode)
        exit(1)
    server_class = globals()[mode.title()]

    storage_nw_ip = os.environ.get('X_CSI_STORAGE_NW_IP')
    persistence_config = _load_json_config('X_CSI_PERSISTENCE_CONFIG',
                                           DEFAULT_PERSISTENCE_CFG)
    cinderlib_config = _load_json_config('X_CSI_CINDERLIB_CONFIG',
                                         DEFAULT_CINDERLIB_CFG)
    backend_config = _load_json_config('X_CSI_BACKEND_CONFIG')
    node_id = _load_json_config('X_CSI_NODE_ID')
    if not backend_config:
        print('Missing required backend configuration')
        exit(2)

    mode_msg = 'in ' + mode + ' only mode ' if mode != 'all' else ''
    print('Starting cinderlib CSI v%s %s(cinderlib: %s, cinder: %s)' %
          (VENDOR_VERSION, mode_msg, cinderlib.__version__, CINDER_VERSION))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # NOTE(geguileo): GRPC library is not compatible with eventlet, so we have
    #                 to hack our way around it proxying objects to run methods
    #                 on native threads.
    state = server._state
    state.server = ServerProxy(state.server)
    state.completion_queue = tpool.Proxy(state.completion_queue)

    csi_plugin = server_class(server, persistence_config, backend_config,
                              cinderlib_config, storage_nw_ip=storage_nw_ip,
                              node_id=node_id)
    print('Running backend %s v%s' %
          (type(csi_plugin.backend.driver).__name__,
           csi_plugin.backend.get_version()))

    server.add_insecure_port(endpoint)
    server.start()
    print('Now serving on %s...' % endpoint)

    try:
        while True:
            time.sleep(ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    main()
