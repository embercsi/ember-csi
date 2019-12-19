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

NAME = 'ember-csi.io'
REVERSE_NAME = 'io.ember-csi'
ENDPOINT = '[::]:50051'
MODE = 'all'
PERSISTENCE_CFG = {'storage': 'crd', 'namespace': 'default'}
ROOT_HELPER = 'sudo'
STATE_PATH = '/var/lib/ember-csi'
VOL_BINDS_DIR = '$state_path/vols'
LOCKS_DIR = '$state_path/locks'
REQUEST_MULTIPATH = False
WORKERS = 30
ENABLE_PROBE = False
HAS_SLOW_OPERATIONS = True
EMBER_CFG = {'project_id': NAME, 'user_id': NAME, 'plugin_name': '',
             'root_helper': ROOT_HELPER,
             'request_multipath': REQUEST_MULTIPATH,
             'file_locks_path': LOCKS_DIR, 'state_path': STATE_PATH,
             'enable_probe': ENABLE_PROBE, 'grpc_workers': WORKERS,
             'slow_operations': HAS_SLOW_OPERATIONS, 'disabled': tuple()}

LOGGING_FORMAT = ('%(asctime)s %(project_name)s %(levelname)s %(name)s '
                  '[%(request_id)s] %(message)s')

LOG_LEVELS = ('amqp=WARN', 'amqplib=WARN', 'boto=WARN', 'qpid=WARN',
              'sqlalchemy=WARN', 'suds=WARN', 'oslo.messaging=WARN',
              'oslo_messaging=WARN', 'iso8601=WARN',
              'requests.packages.urllib3.connectionpool=WARN',
              'urllib3.connectionpool=WARN', 'websocket=WARN',
              'requests.packages.urllib3.util.retry=WARN',
              'urllib3.util.retry=WARN', 'keystonemiddleware=WARN',
              'routes.middleware=WARN', 'stevedore=WARN', 'taskflow=WARN',
              'keystoneauth=WARN', 'oslo.cache=WARN',
              'dogpile.core.dogpile=WARN', 'cinderlib=WARN', 'cinder=WARN',
              'os_brick=WARN')

DEBUG_LOG_LEVELS = ('amqp=WARN', 'amqplib=WARN', 'boto=WARN', 'qpid=WARN',
                    'sqlalchemy=WARN', 'suds=INFO', 'oslo.messaging=INFO',
                    'oslo_messaging=INFO', 'iso8601=WARN',
                    'requests.packages.urllib3.connectionpool=WARN',
                    'urllib3.connectionpool=WARN', 'websocket=WARN',
                    'requests.packages.urllib3.util.retry=WARN',
                    'urllib3.util.retry=WARN', 'keystonemiddleware=WARN',
                    'routes.middleware=WARN', 'stevedore=WARN',
                    'taskflow=WARN', 'keystoneauth=WARN', 'oslo.cache=INFO',
                    'dogpile.core.dogpile=INFO')

MOUNT_FS = 'ext4'
MKFS = '/sbin/mkfs.'
VOLUME_SIZE = 1.0
SPEC_VERSION = '0.2.0'
CRD_NAMESPACE = 'default'
