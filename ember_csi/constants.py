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
from datetime import datetime

import pkg_resources
import pytz


NANOSECONDS = 10 ** 9
EPOCH = datetime.utcfromtimestamp(0).replace(tzinfo=pytz.UTC)
GB = float(1024 ** 3)
ONE_DAY_IN_SECONDS = 60 * 60 * 24
CINDER_VERSION = pkg_resources.get_distribution('cinder').version
CINDERLIB_VERSION = pkg_resources.get_distribution('cinderlib').version
REFRESH_TIME = 1
VENDOR_VERSION = '0.9.1'
MULTIPATH_FIND_RETRIES = 3

SUPPORTED_SPEC_VERSIONS = ('0.2.0', '0.3.0', '1.0.0', '1.1.0')

ERROR_BIND_PORT = 1
ERROR_MODE = 2
ERROR_MISSING_BACKEND = 3
ERROR_TAR = 4
ERROR_FS_TYPE = 5
ERROR_CSI_SPEC = 6
ERROR_TOPOLOGY_UNSUPPORTED = 7
ERROR_TOPOLOGY_JSON = 8
ERROR_TOPOLOGY_MISSING = 9
ERROR_TOPOLOGY_LIST = 10
ERROR_PLUGIN_NAME = 11
ERROR_JSON = 12
ERROR_DEBUG_MODE = 13


BACKEND_KEY_MAPPINGS = (('driver', 'volume_driver'),
                        ('multipath', 'use_multipath_for_image_xfer'),
                        ('name', 'volume_backend_name'))

CLONE_FEATURE = 'clone'
SNAPSHOT_FEATURE = 'snapshot'
EXPAND_FEATURE = 'expand'
EXPAND_ONLINE_FEATURE = 'expand_online'
BLOCK_RWX_FEATURE = 'block_rwx'

CAPABILITY_KEY = '_capability'
CAPABILITIES_KEY = '_capabilities'
PUBLISHED_CAPABILITY_KEY = '_pub_cap'
