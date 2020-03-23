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


INCOMPATIBLE_SINGLE = ('Single access mode not compatible with already '
                       'existing published modes')
INCOMPATIBLE_REQUESTED_CAPABILITY = ('Volume was not created with a '
                                     'compatible capability to the requested '
                                     'one.')
INCOMPATIBLE_MULTI_CAP = ('Volume already published with incompatible multi '
                          'access mode')
MULTIPLE_RW = "Volume published as RXWO and there's already a WR"
INCOMPATIBLE_CAP_PATH = ('Volume already published in that path with '
                         'different capabilities')
ALREADY_PUBLISHED_CAP = ('Volume already published on that node with '
                         'different capabilities')
