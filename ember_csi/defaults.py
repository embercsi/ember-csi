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

NAME = 'io.ember-csi'
ENDPOINT = '[::]:50051'
MODE = 'all'
PERSISTENCE_CFG = {'storage': 'db', 'connection': 'sqlite:///db.sqlite'}
EMBER_CFG = {'project_id': NAME, 'user_id': NAME, 'plugin_name': NAME,
             'root_helper': 'sudo', 'request_multipath': True}
REQUEST_MULTIPATH = True
MOUNT_FS = 'ext4'
MKFS = '/sbin/mkfs.'
VOLUME_SIZE = 1.0
SPEC_VERSION = '0.2.0'
