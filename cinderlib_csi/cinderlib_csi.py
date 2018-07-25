#!/usr/bin/env python

# Supports CSI v0.2.0
# TODO(geguileo): Check that all parameters are present on received RPC calls
from concurrent import futures
import contextlib
from datetime import datetime
import functools
import glob
import itertools
import json
import os
import socket
import stat
import sys
import threading
import time
import traceback

import cinderlib
from eventlet import tpool
import grpc
from os_brick.initiator import connector as brick_connector
from oslo_concurrency import processutils as putils
import pkg_resources
import pytz

import csi_pb2_grpc as csi
import csi_types as types


NAME = 'com.redhat.cinderlib-csi'
VENDOR_VERSION = '0.0.2'
CSI_SPEC = '0.2.0'

DEFAULT_ENDPOINT = '[::]:50051'
DEFAULT_SIZE = 1.0
DEFAULT_PERSISTENCE_CFG = {'storage': 'db',
                           'connection': 'sqlite:///db.sqlite'}
DEFAULT_CINDERLIB_CFG = {'project_id': NAME, 'user_id': NAME,
                         'root_helper': 'sudo'}
DEFAULT_MOUNT_FS = 'ext4'
REFRESH_TIME = 1
MULTIPATH_FIND_RETRIES = 3

GB = float(1024 ** 3)
ONE_DAY_IN_SECONDS = 60 * 60 * 24
CINDER_VERSION = pkg_resources.get_distribution('cinder').version
NANOSECONDS = 10 ** 9
EPOCH = datetime.utcfromtimestamp(0).replace(tzinfo=pytz.UTC)

ABORT_DUPLICATES = (
    (os.environ.get('X_CSI_ABORT_DUPLICATES') or '').upper() == 'TRUE')

locks = {}


def no_debug(f):
    return f


def debug(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        global DEBUG_ON
        if DEBUG_ON:
            DEBUG_LIBRARY.set_trace()
        return f(*args, **kwargs)
    return wrapper


def setup_debug():
    def toggle_debug(signum, stack):
        global DEBUG_ON
        DEBUG_ON = not DEBUG_ON
        sys.stdout.write('Debugging is %s\n' % ('ON' if DEBUG_ON else 'OFF'))

    debug_mode = str(os.environ.get('X_CSI_DEBUG_MODE') or '').upper()
    if debug_mode not in ('', 'PDB', 'RPDB'):
        sys.stderr.write('Invalid X_CSI_DEBUG_MODE %s (valid values are PDB '
                         'and RPDB)\n' % debug_mode)
        exit(3)

    if not debug_mode:
        return None, no_debug

    if debug_mode == 'PDB':
        import pdb as debug_library
    else:
        import rpdb as debug_library

    import signal
    signal.signal(signal.SIGUSR1, toggle_debug)

    return debug_library, debug


DEBUG_ON = False
DEBUG_LIBRARY, debuggable = setup_debug()


def date_to_nano(date):
    # Don't use str or six.text_type, as they truncate
    return repr((date - EPOCH).total_seconds() * NANOSECONDS)


def nano_to_date(nanoseconds):
    date = datetime.utcfromtimestamp(float(nanoseconds)/NANOSECONDS)
    return date.replace(tzinfo=pytz.UTC)


def logrpc(f):
    def tab(what):
        return '\t' + '\n\t'.join(filter(None, str(what).split('\n')))

    @functools.wraps(f)
    def dolog(self, request, context):
        req_id = id(request)
        start = datetime.utcnow()
        if request.ListFields():
            msg = ' params\n%s' % tab(request)
        else:
            msg = 'out params'
        sys.stdout.write('=> %s GRPC [%s]: %s with%s\n' %
                         (start, req_id, f.__name__, msg))
        try:
            result = f(self, request, context)
        except Exception as exc:
            end = datetime.utcnow()
            if context._state.code:
                code = str(context._state.code)[11:]
                details = context._state.details
                tback = ''
            else:
                code = 'Unexpected exception'
                details = exc.message
                tback = '\n' + tab(traceback.format_exc())
            sys.stdout.write('!! %s GRPC in %.0fs [%s]: %s on %s (%s)%s\n' %
                             (end, (end - start).total_seconds(), req_id, code,
                              f.__name__, details, tback))
            raise
        end = datetime.utcnow()
        if str(result):
            str_result = '\n%s' % tab(result)
        else:
            str_result = ' nothing'
        sys.stdout.write('<= %s GRPC in %.0fs [%s]: %s returns%s\n' %
                         (end, (end - start).total_seconds(), req_id,
                          f.__name__, str_result))
        return result
    return dolog


def require(*fields):
    fields = set(fields)

    def join(what):
        return ', '.join(what)

    def func_wrapper(f):
        @functools.wraps(f)
        def checker(self, request, context):
            request_fields = {f[0].name for f in request.ListFields()}
            missing = fields - request_fields
            if missing:
                msg = 'Missing required fields: %s' % join(missing)
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)
            return f(self, request, context)
        return checker
    return func_wrapper


@contextlib.contextmanager
def noop_cm():
    yield


class Worker(object):
    current_workers = {}

    @classmethod
    def _unique_worker(cls, func, request_field):
        @functools.wraps(func)
        def wrapper(self, request, context):
            global locks

            worker_id = getattr(request, request_field)
            my_method = func.__name__
            my_thread = threading.current_thread().ident
            current = (my_method, my_thread)

            if ABORT_DUPLICATES:
                lock = noop_cm()
            else:
                lock = locks.get(my_method)
                if not lock:
                    lock = locks[my_method] = threading.Lock()

            with lock:
                method, thread = cls.current_workers.setdefault(worker_id,
                                                                current)

                if (method, thread) != current:
                    context.abort(
                        grpc.StatusCode.ABORTED,
                        'Cannot %s on %s while thread %s is doing %s' %
                        (my_method, worker_id, thread, method))

                try:
                    return func(self, request, context)
                finally:
                    del cls.current_workers[worker_id]
        return wrapper

    @classmethod
    def unique(cls, *args):
        if len(args) == 1 and callable(args[0]):
            return cls._unique_worker(args[0], 'volume_id')
        else:
            return functools.partial(cls._unique_worker,
                                     request_field=args[0])


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
    def set(cls, node_id, storage_nw_ip):
        if not storage_nw_ip:
            storage_nw_ip = socket.gethostbyname(socket.gethostname())

        # For now just set multipathing and not enforcing it
        connector_dict = brick_connector.get_connector_properties(
            'sudo', storage_nw_ip, True, False)
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
    MKFS = '/sbin/mkfs.'
    DEFAULT_MKFS_ARGS = tuple()
    MKFS_ARGS = {'ext4': ('-F',)}

    def __init__(self, server, cinderlib_cfg):
        if self.manifest is not None:
            return

        self.root_helper = (cinderlib_cfg or {}).get('root_helper') or 'sudo'

        manifest = {
            'cinderlib-version': cinderlib.__version__,
            'cinder-version': CINDER_VERSION,
        }
        self.persistence = cinderlib.Backend.persistence
        manifest['persistence'] = type(self.persistence).__name__

        manifest['mode'] = type(self).__name__.lower()

        if self.backend:
            manifest['cinder-driver-version'] = self.backend.get_version()
            manifest['cinder-driver'] = type(self.backend.driver).__name__
            manifest['cinder-driver-supported'] = str(self.backend.supported)

        self.INFO = types.InfoResp(name=NAME,
                                   vendor_version=VENDOR_VERSION,
                                   manifest=manifest)

        csi.add_IdentityServicer_to_server(self, server)
        self.manifest = manifest
        self.supported_fs_types = self._get_system_fs_types()
        if DEFAULT_MOUNT_FS not in self.supported_fs_types:
            sys.stderr.write('Invalid default mount filesystem %s\n' %
                             DEFAULT_MOUNT_FS)
            exit(1)

    @classmethod
    def _get_system_fs_types(cls):
        fs_types = glob.glob(cls.MKFS + '*')
        start = len(cls.MKFS)
        result = [fst[start:] for fst in fs_types]
        print('Supported filesystems are: %s' % ', '.join(result))
        return result

    def _unsupported_mode(self, capability):
        return capability.access_mode.mode not in self.SUPPORTED_ACCESS

    def _unsupported_fs_type(self, capability):
        # TODO: validate mount_flags
        return (capability.HasField('mount') and
                capability.mount.fs_type and
                capability.mount.fs_type not in self.supported_fs_types)

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

    @debuggable
    @logrpc
    def GetPluginInfo(self, request, context):
        return self.INFO

    @debuggable
    @logrpc
    def GetPluginCapabilities(self, request, context):
        return self.CAPABILITIES

    @debuggable
    @logrpc
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
                 cinderlib_config=None, default_size=DEFAULT_SIZE, **kwargs):
        self.default_size = default_size
        cinderlib.setup(persistence_config=persistence_config,
                        **cinderlib_config)
        self.backend = cinderlib.Backend(**backend_config)
        Identity.__init__(self, server, cinderlib_config)
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

    @debuggable
    @logrpc
    @require('name', 'volume_capabilities')
    @Worker.unique('name')
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

        volume = types.Volume(capacity_bytes=int(vol.size * GB),
                              id=vol.id,
                              attributes=request.parameters)
        return types.CreateResp(volume=volume)

    @debuggable
    @logrpc
    @require('volume_id')
    @Worker.unique
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

    @debuggable
    @logrpc
    @require('volume_id', 'node_id', 'volume_capability')
    @Worker.unique
    def ControllerPublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)

        # The volume is already attached
        if vol.status == 'in-use':
            for conn in vol.connections:
                # TODO(geguileo): Change when we enable multi-attach
                if conn.attached_host != request.node_id:
                    context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                                  'Volume published to another node')

            # TODO(geguileo): Check capabilities and readonly compatibility
            #                 and raise ALREADY_EXISTS if not compatible
            conn = vol.connections[0]
        else:
            conn = vol.connect(node.connector_dict, attached_host=node.id)
        publish_info = {'connection_info': json.dumps(conn.connection_info)}
        return types.CtrlPublishResp(publish_info=publish_info)

    @debuggable
    @logrpc
    @require('volume_id')
    @Worker.unique
    def ControllerUnpublishVolume(self, request, context):
        vol, node = self._get_vol_node(request, context)
        for conn in vol.connections:
            if node is None or conn.attached_host == node.id:
                conn.disconnect()
        return self.CTRL_UNPUBLISH_RESP

    @debuggable
    @logrpc
    @require('volume_id', 'volume_capabilities')
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

    @debuggable
    @logrpc
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

    @debuggable
    @logrpc
    def GetCapacity(self, request, context):
        self._validate_capabilities(request.volume_capabilities, context)
        # TODO(geguileo): Take into account over provisioning values
        stats = self.backend.stats(refresh=True)
        if 'pools' in stats:
            stats = stats['pools'][0]
        free = stats['free_capacity_gb']

        # TODO(geguileo): Confirm available capacity is in bytes
        return types.CapacityResp(available_capacity=int(free * GB))

    @debuggable
    @logrpc
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

    @debuggable
    @logrpc
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
            size_bytes=int(snap.volume_size * GB),
            id=snap.id,
            source_volume_id=vol.id,
            created_at=date_to_nano(snap.created_at),
            status=types.SnapStatus(types.SnapshotStatusType.READY))
        return types.CreateSnapResp(snapshot=snapshot)

    @debuggable
    @logrpc
    def DeleteSnapshot(self, request, context):
        snap = self._get_snap(request.snapshot_id)
        if not snap:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          'Snapshot %s does not exist' % request.snapshot_id)
        snap.delete()
        return self.DELETE_SNAP_RESP

    @debuggable
    @logrpc
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

    def __init__(self, server, persistence_config=None, cinderlib_config=None,
                 node_id=None, storage_nw_ip=None, **kwargs):
        if persistence_config:
            cinderlib_config['fail_on_missing_backend'] = False
            cinderlib.setup(persistence_config=persistence_config,
                            **cinderlib_config)
            Identity.__init__(self, server, cinderlib_config)

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
        cmd = [self.MKFS + fs_type]
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

    @debuggable
    @logrpc
    @require('volume_id', 'staging_target_path', 'volume_capability')
    @Worker.unique
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
            for i in range(MULTIPATH_FIND_RETRIES):
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
                           DEFAULT_MOUNT_FS)
                self._format_device(fs_type, private_bind, context)
                self._mount(fs_type,
                            request.volume_capability.mount.mount_flags,
                            private_bind, target)
        return self.STAGE_RESP

    @debuggable
    @logrpc
    @require('volume_id', 'staging_target_path')
    @Worker.unique
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

    @debuggable
    @logrpc
    @require('volume_id', 'staging_target_path', 'target_path',
             'volume_capability')
    @Worker.unique
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

    @debuggable
    @logrpc
    @require('volume_id', 'target_path')
    @Worker.unique
    def NodeUnpublishVolume(self, request, context):
        device = self._get_device(request.target_path)
        if device:
            self.sudo('umount', request.target_path, retries=4)
        return self.NODE_UNPUBLISH_RESP

    @debuggable
    @logrpc
    def NodeGetId(self, request, context):
        return self.node_id

    @debuggable
    @logrpc
    def NodeGetCapabilities(self, request, context):
        rpc = types.NodeCapabilityType.STAGE_UNSTAGE_VOLUME
        capabilities = [types.NodeCapability(rpc=types.NodeRPC(type=rpc))]
        return types.NodeCapabilityResp(capabilities=capabilities)


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
    global DEFAULT_MOUNT_FS
    # CSI_ENDPOINT should accept multiple formats 0.0.0.0:5000, unix:foo.sock
    endpoint = os.environ.get('CSI_ENDPOINT', DEFAULT_ENDPOINT)
    mode = os.environ.get('CSI_MODE') or 'all'
    DEFAULT_MOUNT_FS = os.environ.get('X_CSI_DEFAULT_MOUNT_FS',
                                      DEFAULT_MOUNT_FS)
    if mode not in ('controller', 'node', 'all'):
        sys.stderr.write('Invalid mode value (%s)\n' % mode)
        exit(1)
    server_class = globals()[mode.title()]

    storage_nw_ip = os.environ.get('X_CSI_STORAGE_NW_IP')
    persistence_config = _load_json_config('X_CSI_PERSISTENCE_CONFIG',
                                           DEFAULT_PERSISTENCE_CFG)
    cinderlib_config = _load_json_config('X_CSI_CINDERLIB_CONFIG',
                                         DEFAULT_CINDERLIB_CFG)
    backend_config = _load_json_config('X_CSI_BACKEND_CONFIG')
    node_id = os.environ.get('X_CSI_NODE_ID')
    if mode != 'node' and not backend_config:
        print('Missing required backend configuration')
        exit(2)

    mode_msg = 'in ' + mode + ' only mode ' if mode != 'all' else ''
    print('Starting cinderlib CSI v%s %s(cinderlib: v%s, cinder: v%s, '
          'CSI spec: v%s)' %
          (VENDOR_VERSION, mode_msg, cinderlib.__version__, CINDER_VERSION,
           CSI_SPEC))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # NOTE(geguileo): GRPC library is not compatible with eventlet, so we have
    #                 to hack our way around it proxying objects to run methods
    #                 on native threads.
    state = server._state
    state.server = ServerProxy(state.server)
    state.completion_queue = tpool.Proxy(state.completion_queue)

    csi_plugin = server_class(server=server,
                              persistence_config=persistence_config,
                              backend_config=backend_config,
                              cinderlib_config=cinderlib_config,
                              storage_nw_ip=storage_nw_ip,
                              node_id=node_id)
    msg = 'Running as %s' % mode
    if mode != 'node':
        driver_name = type(csi_plugin.backend.driver).__name__
        msg += ' with backend %s v%s' % (driver_name,
                                         csi_plugin.backend.get_version())
    print(msg)

    print('Debugging feature is %s.' %
          ('ENABLED with %s and OFF. Toggle it with SIGUSR1' %
           DEBUG_LIBRARY.__name__ if DEBUG_LIBRARY else 'DISABLED'))

    if not server.add_insecure_port(endpoint):
        sys.stderr.write('\nERROR: Could not bind to %s\n' % endpoint)
        exit(1)

    server.start()
    print('Now serving on %s...' % endpoint)

    try:
        while True:
            time.sleep(ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    main()
