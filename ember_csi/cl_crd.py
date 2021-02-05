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
"""CRD metadata persistence plugin

The identifier for this plugin when using it in the X_CSI_PERSISTENCE_CONFIG
environmental variable is "crd".

All Ember-CSI containers (node and controllers) must have the following
RBACs::

   # Allow listing and creating CRDs
   - apiGroups: ['apiextensions.k8s.io']
     resources: ['customresourcedefinitions']
     verbs: ['list', 'create']

   # Allow managing Ember resources
   - apiGroups: ["ember-csi.io"]
     resources: ["*"]
     verbs: ["*"]

Our Custom Resource Objects can be listed with their singular, plural, and
short names::

    kubectl get vol
    kubectl get volume
    kubectl get volumes

    kubectl get snap
    kubectl get snapshot
    kubectl get snapshots

    kubectl get conn
    kubectl get connection
    kubectl get connections

    kubectl get kv
    kubectl get keyvalue
    kubectl get keyvalues

Since they are added to the all and ember categories we can also see them
with::

    kubectl get all
    kubectl get ember

This plugin is not watching the CROs and acting on changes, so we should not be
creating/deleting/changing them via kubectl, but through the CSI interface
instead.
"""
from __future__ import absolute_import
import os

import cinderlib
from cinderlib import objects
from cinderlib.persistence import base
import kubernetes as k8s
from oslo_log import log as logging
import six

from ember_csi import defaults
from ember_csi import workarounds


LOG = logging.getLogger(__name__)


class CRD(object):
    """CRD base class.

    Each one of the Custom Resource Objects created will use labels to make
    Kubernetes do the search on the objects, and the cinderlib object's JSON
    data will be stored as an annotation called `json`.

    In the future we may want to do this more efficiently: have individual
    annotation fields and use patch to only update changes.

    The CRDs are added to the "all" and "ember" categories.
    """
    CRD_VERSION = 'v1'
    DOMAIN = defaults.NAME
    NAMESPACE = defaults.CRD_NAMESPACE
    RESOURCE_VERSION_ATTR = '__resource_version'

    @classmethod
    def ensure_crds_exist(cls):
        """Ensure CRDs are present in Kubernetes.

        Checks existing CRDs and searches for our 4 CRDs: Volume, Snapshot,
        Connection, KeyValue.  If any of them doesn't exist it is created.

        It also initializes our CRDs' class attributes: kind, singular, plural,
        api_name, and api_version.
        """
        crds = K8S.ext_api.list_custom_resource_definition().to_dict()['items']
        current_crds = [crd['spec']['names']['kind'] for crd in crds]
        for crd in cls.__subclasses__():
            # Initialize class attributes
            crd.kind = crd.__name__
            crd.singular = crd.kind.lower()
            crd.plural = crd.singular + 's'
            crd.api_name = crd.plural + '.' + crd.DOMAIN
            crd.api_version = crd.DOMAIN + '/' + crd.CRD_VERSION

            if crd.__name__ not in current_crds:
                try:
                    crd.create_crd_definition()
                except k8s.client.rest.ApiException as exc:
                    # If it already exists, ignore this error.
                    if exc.status != 409:
                        raise

    @classmethod
    def create_crd_definition(cls):
        """Creates a CRD definition for the current class.

        The CRDs are added to the "all" and "ember" categories, making it
        possible to list them with

            kubectl get all
            kubectl get ember

        As well as with the individual names and shortcuts.
        """
        crd = {'apiVersion': 'apiextensions.k8s.io/v1beta1',
               'kind': 'CustomResourceDefinition',
               'metadata': {'name': cls.api_name},
               'spec': {'group': cls.DOMAIN,
                        'version': cls.CRD_VERSION,
                        'scope': 'Namespaced',
                        'names': {'kind': cls.kind,
                                  'singular': cls.singular,
                                  'plural': cls.plural,
                                  'shortNames': [cls.SHORTNAME],
                                  'categories': ['all', 'ember']}}}
        K8S.ext_api.create_custom_resource_definition(crd)

    @staticmethod
    def _prepare_labels(labels):
        """Prepare labels for K8s, removing empty and splitting long ones."""
        result = {}
        for k, v in labels.items():
            if not v:
                continue
            # Split strings that are too long
            if isinstance(v, six.string_types) and len(v) > 63:
                j = 2
                for i in range(63, len(v), 63):
                    key = '%s%s' % (k, j)
                    result[key] = v[i:i+63]
                    j += 1
                v = v[:63]
            result[k] = v
        return result

    @classmethod
    def get(cls, **kwargs):
        """Get a cinderlib object.

        Positional arguments are used as label selectors.

        Received CROs are then deserialized using cinderlib's load method.
        """
        selector = cls._prepare_labels(kwargs)
        res_id = selector.get(cls.singular + '_id')
        if res_id is not None:
            try:
                res = K8S.crd_api.get_namespaced_custom_object(cls.DOMAIN,
                                                               cls.CRD_VERSION,
                                                               cls.NAMESPACE,
                                                               cls.plural,
                                                               res_id)
            except k8s.client.rest.ApiException as exc:
                if exc.status == 404:
                    return []
                raise

            # Check that the other fields also match
            for k, v in selector.items():
                if res['metadata']['labels'][k] != v:
                    LOG.error("%s %s has wrong label %s. %s != %s",
                              cls.kind, res_id, k, v,
                              res['metadata']['labels'][k])
                    return []
            res = [res]
        else:
            selector_str = ','.join(k + '=' + v for k, v in selector.items())
            res = K8S.crd_api.list_namespaced_custom_object(
                cls.DOMAIN, cls.CRD_VERSION, cls.NAMESPACE, cls.plural,
                label_selector=selector_str, resource_version='', watch=False)
            res = res['items']

        result = []
        for item in res:
            resource_json = item['metadata']['annotations']['json']
            resource = cinderlib.load(resource_json)
            cls._set_resource_version(resource, item)
            result.append(resource)
        return result

    @classmethod
    def delete(cls, name):
        """Delete a CRO based on its name."""
        try:
            K8S.crd_api.delete_namespaced_custom_object(cls.DOMAIN,
                                                        cls.CRD_VERSION,
                                                        cls.NAMESPACE,
                                                        cls.plural,
                                                        name=name,
                                                        body={})
        except k8s.client.rest.ApiException as exc:
            if exc.status != 404:
                raise

    @classmethod
    def set(cls, resource, is_new=None):
        """Sets the JSON of a cinderlib object in a CRO.

        Creates labels to facilitate filtering when retrieving them.
        """
        json_data = resource.to_jsons(simplified=True)
        labels = cls._prepare_labels(cls._get_labels(resource))
        cro = {'kind': cls.kind,
               'apiVersion': cls.api_version,
               'metadata': {'labels': labels,
                            'name': resource.id,
                            'annotations': {'json': json_data}}}
        cls._set_dict_resource_version(resource, cro)
        res = cls._apply(resource.id, cro, is_new)
        cls._set_resource_version(resource, res)

    @classmethod
    def _apply(cls, name, body, is_new):
        """Ensure CRO exists, creating or updating it as necessary.

        resourceVersion is used as a rough mechanism to prevent concurrent
        changes.
        """
        def replace():
            return K8S.crd_api.replace_namespaced_custom_object(
                cls.DOMAIN,
                cls.CRD_VERSION,
                cls.NAMESPACE,
                cls.plural,
                name,
                body)

        def create():
            return K8S.crd_api.create_namespaced_custom_object(cls.DOMAIN,
                                                               cls.CRD_VERSION,
                                                               cls.NAMESPACE,
                                                               cls.plural,
                                                               body)

        if is_new:
            return create()

        elif body['metadata'].get('resourceVersion') is not None:
            return replace()

        else:
            try:
                res = K8S.crd_api.get_namespaced_custom_object(cls.DOMAIN,
                                                               cls.CRD_VERSION,
                                                               cls.NAMESPACE,
                                                               cls.plural,
                                                               name)
                body['metadata']['resourceVersion'] = (
                    res['metadata']['resourceVersion'])
                return replace()
            except Exception as exc:
                if exc.status != 404:
                    raise
                return create()

    @classmethod
    def _set_resource_version(cls, resource, result):
        setattr(resource,
                cls.RESOURCE_VERSION_ATTR,
                result['metadata']['resourceVersion'])

    @classmethod
    def _set_dict_resource_version(cls, resource, body):
        version = getattr(resource, cls.RESOURCE_VERSION_ATTR, None)
        if version is not None:
            body['metadata']['resourceVersion'] = version


class Volume(CRD):
    """CRD representation for volumes.

    Volumes are create with 3 labels to facilitate their search:
        - id
        - display_name
        - backend
    """
    SHORTNAME = 'vol'

    @classmethod
    def _get_labels(cls, volume):
        # On controllers volume.backend is a backend object, a string on nodes
        return {
            'backend_name': getattr(volume.backend, 'id', volume.backend),
            'volume_id': volume.id,
            'volume_name': volume.name,
        }


class Snapshot(CRD):
    """CRD representation for snapshots.

    Snapshots are create with 3 labels to facilitate their search:
        - snapshot_id
        - snapshot_name
        - volume_id
    """
    SHORTNAME = 'snap'

    @classmethod
    def _get_labels(cls, snapshot):
        return {
            'snapshot_id': snapshot.id,
            'snapshot_name': snapshot.name,
            'volume_id': snapshot.volume_id,
        }


class Connection(CRD):
    """CRD representation for snapshots.

    Connections are create with 2 labels to facilitate their search:
        - connection_id
        - volume_id
    """
    SHORTNAME = 'conn'

    @classmethod
    def _get_labels(cls, connection):
        return {
            'connection_id': connection.id,
            'volume_id': connection.volume_id,
        }


class KeyValue(CRD):
    """CRD storage class for Key-Value pairs.

    If this were an independent cinderlib metadata plugin we would have to
    store the key as a label and use list to retrieve the values, but since we
    know we only write 1 key-value pair we'll use get instead.

    This doesn't use CRD base class methods for get and set, because the key-
    values are not a real Cinder object, so they don't follow the same rules as
    volumes, snapshots, and connections.

    This Custom Resource Object won't have any label.  The key will be the name
    and the value will be stored in a `value` annotation.
    """
    SHORTNAME = 'kv'

    @classmethod
    def get(cls, key):
        """Gets a KeyValue CRO and returns a cinderlib KeyValue."""
        try:
            res = K8S.crd_api.get_namespaced_custom_object(cls.DOMAIN,
                                                           cls.CRD_VERSION,
                                                           cls.NAMESPACE,
                                                           cls.plural,
                                                           key)
            kv = objects.KeyValue(key, res['metadata']['annotations']['value'])
            cls._set_resource_version(kv, res)
            return([kv])
        except k8s.client.rest.ApiException as exc:
            if exc.status == 404:
                return []
            raise

    @classmethod
    def set(cls, key_value, is_new=None):
        """Sets the value of a cinderlib KeyValue in a CRO."""
        cro = {'kind': cls.kind,
               'apiVersion': cls.api_version,
               'metadata': {'name': key_value.key,
                            'annotations': {'value': key_value.value}}}
        cls._set_dict_resource_version(key_value, cro)
        res = cls._apply(key_value.key, cro, is_new)
        cls._set_resource_version(key_value, res)


class CRDPersistence(base.PersistenceDriverBase):
    """Kubernetes CRD metadata persistence plugin for cinderlib.

    This is an opinionated implementation that takes into account our specific
    use case.
    """
    def __init__(self, namespace=None, **kwargs):
        # Create fake DB for drivers
        self.fake_db = base.DB(self)
        if namespace:
            CRD.NAMESPACE = namespace
        CRD.ensure_crds_exist()
        super(CRDPersistence, self).__init__()

    @property
    def db(self):
        return self.fake_db

    def get_volumes(self, volume_id=None, volume_name=None, backend_name=None):
        return Volume.get(volume_id=volume_id, volume_name=volume_name,
                          backend_name=backend_name)

    def get_snapshots(self, snapshot_id=None, snapshot_name=None,
                      volume_id=None):
        return Snapshot.get(snapshot_id=snapshot_id,
                            snapshot_name=snapshot_name,
                            volume_id=volume_id)

    def get_connections(self, connection_id=None, volume_id=None):
        return Connection.get(connection_id=connection_id, volume_id=volume_id)

    def get_key_values(self, key):
        return KeyValue.get(key)

    def set_volume(self, volume):
        Volume.set(volume,
                   'id' in self.get_changed_fields(volume))
        super(CRDPersistence, self).set_volume(volume)

    def set_snapshot(self, snapshot):
        Snapshot.set(snapshot,
                     'id' in self.get_changed_fields(snapshot))
        super(CRDPersistence, self).set_snapshot(snapshot)

    def set_connection(self, connection):
        Connection.set(connection,
                       'id' in self.get_changed_fields(connection))
        super(CRDPersistence, self).set_connection(connection)

    def set_key_value(self, key_value):
        KeyValue.set(key_value)

    def delete_volume(self, volume):
        Volume.delete(volume.id)
        super(CRDPersistence, self).delete_volume(volume)

    def delete_snapshot(self, snapshot):
        Snapshot.delete(snapshot.id)
        super(CRDPersistence, self).delete_snapshot(snapshot)

    def delete_connection(self, connection):
        Connection.delete(connection.id)
        super(CRDPersistence, self).delete_connection(connection)

    def delete_key_value(self, key):
        KeyValue.delete(key)
        super(CRDPersistence, self).delete_key_value(key)


class K8sConnection(object):
    def __init__(self):
        if 'KUBERNETES_PORT' in os.environ:
            k8s.config.load_incluster_config()
        else:
            k8s.config.load_kube_config()
        config = k8s.client.Configuration()
        if config.host.startswith('https://'):
            config.assert_hostname = False
        self.api = k8s.client.api_client.ApiClient(configuration=config)
        self.ext_api = k8s.client.ApiextensionsV1beta1Api(self.api)
        self.crd_api = k8s.client.CustomObjectsApi(self.api)


# GLOBAL INITIALIZATION
# The evenlet workaround must come first
workarounds.eventlet_issue_147_172()
K8S = K8sConnection()
workarounds.k8s_issue_376()
