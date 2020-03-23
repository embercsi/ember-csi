# Copyright (c) 2020, Red Hat, Inc.
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
#
#
# Assumptions made by the Ember-CSI code regarding the capabilities of volumes
# which are by Kubernetes/OpenShift centric in orther to simplify the
# complexities of the checks.
#
# - There will be a single ControllerPublishVolume call for each node and
#   volume, and it will always be made with the most permissions possible.
#   This never comes   with the readonly set to True.
# - There will only be 1 call to NodeStageVolume for each volume, with the less
#   restrictive permissions, just like as the controller publish call, and the
#   readonly flag won't be set either.  Though there's a bug in k8s that may
#   make us get a RW instead of RWX. It can be fixed in the StorageClass by
#   having ReadWriteOnce after ReadWriteMany in accessModes.
# - There can be multiple NodePublishVolume on different paths for the same
#   volume.
# - There is no support for MULTI_NODE_SINGLE_WRITER, so we won't enforce it.

from __future__ import absolute_import
import json

import grpc
from oslo_log import log as logging
import six

from ember_csi import config
from ember_csi import constants
from ember_csi import messages


CONF = config.CONF
CAP_KEY = constants.CAPABILITY_KEY


class ServiceCapabilities(object):
    def __init__(self, can_brwx, can_mrwx):
        self.can_brwx = can_brwx
        self.can_mrwx = can_mrwx

        self.SUPPORTED_ACCESS = Capability.SINGLE_ACCESS_MODES
        if self.can_brwx or self.can_mrwx:
            self.SUPPORTED_ACCESS += Capability.MULTI_ACCESS_MODES

    def unsupported(self, capabilities):
        if not isinstance(capabilities, Capabilities):
            capabilities = Capabilities(capabilities)

        for capability in capabilities:
            # Support for mount and block RWX are independent, so supported
            # mode depends on the access type
            rwx = self.can_brwx if capability.is_block else self.can_mrwx
            if (capability.access_mode not in self.SUPPORTED_ACCESS or
                    capability.multi_mode and not rwx):
                return 'Unsupported access mode'

            # TODO: validate mount_flags
            if (not capability.is_block and
                    capability.fs_type and
                    capability.fs_type not in CONF.SUPPORTED_FS_TYPES):
                return 'Unsupported file system type'

        return None


class Capabilities(object):
    def __init__(self, capabilities):
        if isinstance(capabilities, six.string_types):
            capabilities = json.loads(capabilities)

        self.capabilities = [c if isinstance(c, Capability) else Capability(c)
                             for c in capabilities]
        self._has_multi_mode = None

    @property
    def has_multi_mode(self):
        if self._has_multi_mode is None:
            self._has_multi_mode = any(c.multi_mode for c in self)
        return self._has_multi_mode

    def __iter__(self):
        return iter(self.capabilities)

    def __nonzero__(self):
        return bool(self.capabilities)

    @property
    def json(self):
        return [c.json for c in self]

    @property
    def jsons(self):
        return json.dumps(self.json, separators=(',', ':'))

    def supports(self, capability):
        if not isinstance(capability, Capability):
            capability = Capability(capability)

        return any(cap.supports(capability) for cap in self)


class Capability(object):
    def __init__(self, capability, ro_forced=None):
        if isinstance(capability, six.string_types):
            capability = json.loads(capability)

        if isinstance(capability, dict):
            self.is_block = capability['is_block']
            self.access_mode = capability['access_mode']
            self.fs_type = capability.get('fs_type')
            self.mount_flags = capability.get('mount_flags')
            if ro_forced is None:
                self.ro_forced = capability.get('ro_forced', False)
            else:
                self.ro_forced = ro_forced

        # If it's a gRPC object
        else:
            self.is_block = capability.HasField('block')
            self.access_mode = capability.access_mode.mode
            if self.is_block:
                self.fs_type = None
                self.mount_flags = None
            else:
                self.fs_type = (capability.mount.fs_type or
                                CONF.DEFAULT_MOUNT_FS)
                self.mount_flags = list(capability.mount.mount_flags)
            self.ro_forced = ro_forced or False

        self.ro_mode = self.access_mode in self.RO_ACCESS_MODES
        self.multi_mode = self.access_mode not in self.SINGLE_ACCESS_MODES
        self.used_as_ro = self.ro_forced or self.ro_mode

    def __eq__(self, other):
        if not isinstance(other, Capability):
            other = Capability(other)

        res = (self.is_block == other.is_block and
               self.access_mode == other.access_mode and
               self.fs_type == other.fs_type and
               self.mount_flags == other.mount_flags and
               self.ro_forced == other.ro_forced)
        return res

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def json(self):
        res = {'is_block': self.is_block, 'access_mode': self.access_mode,
               'ro_forced': self.ro_forced}
        if not self.is_block:
            res['fs_type'] = self.fs_type
            res['mount_flags'] = self.mount_flags
        return res

    @property
    def jsons(self):
        return json.dumps(self.json, separators=(',', ':'))

    def supports(self, capability):
        if self == capability:
            return True

        # Block and Mount modes are not compatible and our capability must be
        # less restrictive
        if (self.is_block != capability.is_block or
                (not capability.used_as_ro and self.used_as_ro) or
                (capability.multi_mode and not self.multi_mode)):
            return False

            return False

        return (self.is_block or
                (self.fs_type == capability.fs_type and
                 self.mount_flags == capability.mount_flags))

    def incompatible_connections(self, all_conns, exclude=[]):
        all_conns = [c for c in all_conns if c not in exclude]
        if not all_conns:
            return None

        reason = None
        # Single modes are incompatible with everything else, and we have
        # checked before that we haven't published like this here before.
        if not self.multi_mode:
            reason = messages.INCOMPATIBLE_SINGLE

        else:
            check_rw = (self.access_mode == self.MULTI_NODE_SINGLE_WRITER and
                        not self.used_as_ro)

            for conn in all_conns:
                cap = Capability(conn.connector_info[CAP_KEY])

                # All multi modes are incompatible between them
                if cap.access_mode != self.access_mode:
                    reason = messages.INCOMPATIBLE_MULTI_CAP
                    break

                # On multi read with 1 writer ensure we don't have 2
                if check_rw and not cap.used_as_ro:
                    reason = messages.MULTIPLE_RW
                    break

        if not reason:
            return None

        err_code = grpc.StatusCode.FAILED_PRECONDITION
        return err_code, reason

    @classmethod
    def set_access_modes(cls, access_modes):
        cls.SINGLE_NODE_WRITER = access_modes.SINGLE_NODE_WRITER
        cls.SINGLE_NODE_READER_ONLY = access_modes.SINGLE_NODE_READER_ONLY
        cls.MULTI_NODE_READER_ONLY = access_modes.MULTI_NODE_READER_ONLY
        cls.MULTI_NODE_SINGLE_WRITER = access_modes.MULTI_NODE_SINGLE_WRITER
        cls.MULTI_NODE_MULTI_WRITER = access_modes.MULTI_NODE_MULTI_WRITER

        cls.SINGLE_ACCESS_MODES = (cls.SINGLE_NODE_WRITER,
                                   cls.SINGLE_NODE_READER_ONLY)
        cls.MULTI_ACCESS_MODES = (cls.MULTI_NODE_READER_ONLY,
                                  cls.MULTI_NODE_SINGLE_WRITER,
                                  cls.MULTI_NODE_MULTI_WRITER)
        cls.RO_ACCESS_MODES = (cls.SINGLE_NODE_READER_ONLY,
                               cls.MULTI_NODE_READER_ONLY)


set_access_modes = Capability.set_access_modes
