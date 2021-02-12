[![License](https://img.shields.io/:license-apache-blue.svg)](http://www.apache.org/licenses/LICENSE-2.0) [![Docs](https://readthedocs.org/projects/ember-csi/badge/?version=latest)](http://docs.ember-csi.io/) [![PyPi](https://img.shields.io/pypi/v/ember_csi.svg)](https://pypi.python.org/pypi/ember_csi) [![PyVersion](https://img.shields.io/pypi/pyversions/ember_csi.svg)](https://pypi.python.org/pypi/ember_csi)

# Ember CSI - [https://ember-csi.io](https://ember-csi-io)

Multi-vendor CSI plugin driver supporting over 80 storage drivers in a single plugin to provide `block` and `mount` storage to Container Orchestration systems such as Kubernetes and OpenShift.

This CSI driver is up to date with CSI v1.1 specs, supporting the following features:

- Create block volume
- Creating snapshots
- Creating a block volume from a snapshot
- Delete block volume
- Deleting snapshots
- Listing volumes with pagination
- Listing snapshots with pagination
- Attaching volumes
- Detaching volumes
- Reporting storage capacity
- Probing the node
- Retrieving the plugin info

## Quickstart

The easiest way to see Ember-CSI in action is probably using the *testing script*, which deploys a single node OpenShift cluster inside a VM (using [CRC](https://developers.redhat.com/products/codeready-containers/overview)) and then uses the Ember-CSI operator to deploy and LVM driver.

The *testing script* can accommodate other storage backends as well as compile and deploy the operator and storage plugin from source.

**Attention**: The **testing script** will install necessary packages such as KVM, libvirt, tinyproxy...

```
    $ git clone git@github.com:embercsi/crc-tests.git
    $ cd crc-tests
    $ ./start.sh driver
```

After some time the deployment will be completed and a message indicating steps to access the cluster from the command line and web console will be displayed:

```
    If you are running this on a different host/VM, you can access the web console by:
      - Setting your browser's proxy to this host's IP and port 8888
      - Going to https://console-openshift-console.apps-crc.testing
      - Using below credentials (kubeadmin should be entered as kube:admin)
    To login as a regular user, run 'oc login -u developer -p developer https://api.crc.testing:6443'.
    To login as an admin, run 'oc login -u kubeadmin -p dpDFV-xamBW-kKAk3-Fi6Lg https://api.crc.testing:6443'

    To access the cluster from the command line you can run:
      $ eval `/home/vagrant/crc-linux/crc oc-env`
      $ ./start.sh login
```

If we want to SSH into VM running the OpenShift cluster we can use:

```
    $ ./start.sh ssh
```

## Installation

Ember-CSI can be installed using the Ember-CSI operator, using YAML manifests, or via Helm charts.

The recommended mechanism is using the operator, but we also provide example manifests for Kubernetes under `examples/k8s_v1.20-CSI_v1.1/kubeyml/lvm` `examples/k8s_v1.20-CSI_v1.1/kubeyml/rbd`.

Please refer to the [installation documentation](https://docs.ember-csi.io/en/latest/installation.html) for details on how to install Ember-CSI with the operator.

## Requirements

Depending on the configured backend Ember-CSI may require some services to be running on the host.

For iSCSI backends it requires that all the hosts in our deployment are running `iscsid` on the host itself, since Ember-CSI will be using it to do the connections.

If we want to use multipathing for iSCSI or FC connections we'll need the `multipathd` service configured and running on the host as well.

## Dependencies

Some storage backends have additional requirements such as libraries and tools, in most cases these are Python dependencies required on the Controller side.

Some of these Python dependencies are:

- DRBD: `dbus` and `drbdmanage`
- HPE 3PAR: `python-3parclient`
- Kaminario: `krest`
- Pure: `purestorage`
- Dell EMC VMAX, IBM DS8K: `pyOpenSSL`
- HPE Lefthad: `python-lefthandclient`
- Fujitsu Eternus DX: `pywbem`
- IBM XIV: `pyxcli`
- RBD: `rados` and `rbd`
- Dell EMC VNX: `storops`
- Violin: `vmemclient`
- INFINIDAT: `infinisdk`, `capacity`, `infy.dtypes.wwn`, `infi.dtypes.iqn`

Most of these dependencies are included in the Ember-CSI image, but if you try to use a driver that is missing some dependencies, please let us know.

## Support

For any questions or concerns please file an issue with the [ember-csi](https://github.com/akrog/ember-csi/issues) project or ping me on IRC (my handle is geguileo and I hang on the #openstack-cinder channel in Freenode).
