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
REFRESH_TIME = 1
VENDOR_VERSION = '0.0.2'
MULTIPATH_FIND_RETRIES = 3
VENDOR_VERSION = '0.0.2'

SUPPORTED_SPEC_VERSIONS = ('0.2.0',)
