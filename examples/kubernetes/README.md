# Kubernetes setup

This demo is based on Luis Pabon's [Kubeup repository](https://github.com/lpabon/kubeup).

It deploys a Kubernetes single master cluster on CentOS 7 with 2 additional nodes using [kubeadm](http://kubernetes.io/docs/admin/kubeadm/) and cinderlib-CSI as the storage provider with an LVM loopback device as the backend.

CSI driver is set as the default storage class, running 1 service (`StatefulSet`) with the CSI plugin running as *Controller* to manage the provisioning on *node0*, and a service (`DaemonSet`) running the plugin as *Node* mode on each of the nodes to manage local attachments.

This example uses Vagrant, libvirt, KVM, and Ansible to create and provision these 3 VMs.

**These Ansible playbooks are not idempotent, so don't run them more than once**

## Requirements

Install qemu-kvm, libvirt, vagrant-libvirt, and ansible.

* Fedora

```
$ sudo dnf -y install qemu-kvm libvirt vagrant-libvirt ansible
```


## Configuration

Running the demo with the default LVM storage backend requires no configuration changes.

If we want to use a different storage backend we need to edit the `kubeyml/controller.yml` file to change the storage configuration for the CSI plugin. This is done by changing the *value* of the `X_CSI_BACKEND_CONFIG` environmental variable with our own driver configuration.  For more information on the specific driver configuration please refer to the [cinderlib documentation](https://cinderlib.readthedocs.io), specifically to the [Backend section](https://cinderlib.readthedocs.io/en/latest/topics/backends.html), and the [Validated drivers' section](https://cinderlib.readthedocs.io/en/latest/validated_backends.html).

The `Vagranfile` defines 2 nodes and a master, each with 4GB and 2 cores.  This can be changed using variables `NODES`, `MEMORY`, and `CPUS` in this file.


## Setup

The demo supports local and remote libvirt, for those that use an external box where they run their VMs.

Local setup of the demo can be done running the `up.sh` script, be aware that this will take a while:

```
$ ./up.sh
Bringing machine 'master' up with 'libvirt' provider...
Bringing machine 'node0' up with 'libvirt' provider...
Bringing machine 'node1' up with 'libvirt' provider...
==> master: Checking if box 'centos/7' is up to date...
==> node1: Checking if box 'centos/7' is up to date...
==> node0: Checking if box 'centos/7' is up to date...

[ . . . ]

PLAY RECAP *********************************************************************
master                     : ok=35   changed=31   unreachable=0    failed=0
node0                      : ok=33   changed=27   unreachable=0    failed=0
node1                      : ok=25   changed=23   unreachable=0    failed=0
```

Remote configuration requires defining our remote libvirt system using `LIBVIRT_HOST` and `LIBVIRT_USER` environmental variables before calling the `up.sh` script.

`LIBVIRT_USER` defaults to `root`, so we don't need to set it up if that's what we want to use:

```
$ export LIBVIRT_HOST=192.168.1.11
$ ./up.sh
Bringing machine 'master' up with 'libvirt' provider...
Bringing machine 'node0' up with 'libvirt' provider...
Bringing machine 'node1' up with 'libvirt' provider...
==> master: Checking if box 'centos/7' is up to date...
==> node1: Checking if box 'centos/7' is up to date...
==> node0: Checking if box 'centos/7' is up to date...

[ . . . ]

PLAY RECAP *********************************************************************
master                     : ok=35   changed=31   unreachable=0    failed=0
node0                      : ok=33   changed=27   unreachable=0    failed=0
node1                      : ok=25   changed=23   unreachable=0    failed=0
```


## Usage

After the setup is completed the Kubernetes configuration is copied from the master node to the host, so we can use it locally as follows:

```
$ kubectl --kubeconfig=kubeconfig.conf get nodes
master    Ready     master    21m       v1.11.1
node0     Ready     <none>    21m       v1.11.1
node1     Ready     <none>    21m       v1.11.1
```

Or we can just SSH into the master and run commands in there:
```
$ vagrant ssh master
Last login: Tue Jul 24 10:12:40 2018 from 192.168.121.1
[vagrant@master ~]$ kubectl get nodes
NAME      STATUS    ROLES     AGE       VERSION
master    Ready     master    21m       v1.11.1
node0     Ready     <none>    21m       v1.11.1
node1     Ready     <none>    21m       v1.11.1
```

Unless stated otherwise all the following commands are run assuming we are in the *master* node.

We can check that the CSI *controller* service is running:

```
[vagrant@master ~]$ kubectl get pod csi-controller-0
NAME               READY     STATUS    RESTARTS   AGE
csi-controller-0   4/4       Running   0          22m
```

Check the logs of the CSI *controller*:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -c csi-driver
Starting cinderlib CSI v0.0.2 in controller only mode (cinderlib: v0.2.2.dev0, cinder: v11.1.1, CSI spec: v0.2.0)
Supported filesystems are: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
Running as controller with backend LVMVolumeDriver v3.0.0
Debugging feature is ENABLED with cinderlib_csi.rpdb and OFF. Toggle it with SIGUSR1.
Now serving on unix:///csi-data/csi.sock...
=> 2018-07-24 10:14:28.981718 GRPC [126562384]: GetPluginInfo without params
<= 2018-07-24 10:14:28.981747 GRPC in 0s [126562384]: GetPluginInfo returns
        name: "com.redhat.cinderlib-csi"
        vendor_version: "0.0.2"
        manifest {
          key: "cinder-driver"
          value: "LVMVolumeDriver"
        }
        manifest {
          key: "cinder-driver-supported"
          value: "True"
        }
        manifest {
          key: "cinder-driver-version"
          value: "3.0.0"
        }
        manifest {
          key: "cinder-version"
          value: "11.1.1"
        }
        manifest {
          key: "cinderlib-version"
          value: "0.2.2.dev0"
        }
        manifest {
          key: "mode"
          value: "controller"
        }
        manifest {
          key: "persistence"
          value: "CRDPersistence"
        }
=> 2018-07-24 10:14:28.984271 GRPC [126562624]: Probe without params
<= 2018-07-24 10:14:28.984289 GRPC in 0s [126562624]: Probe returns nothing
=> 2018-07-24 10:14:28.986625 GRPC [126562744]: GetPluginCapabilities without params
<= 2018-07-24 10:14:28.986645 GRPC in 0s [126562744]: GetPluginCapabilities returns
        capabilities {
          service {
            type: CONTROLLER_SERVICE
          }
        }
=> 2018-07-24 10:14:28.988548 GRPC [126562864]: ControllerGetCapabilities without params
<= 2018-07-24 10:14:28.988654 GRPC in 0s [126562864]: ControllerGetCapabilities returns
        capabilities {
          rpc {
            type: CREATE_DELETE_VOLUME
          }
        }
        capabilities {
          rpc {
            type: PUBLISH_UNPUBLISH_VOLUME
          }
        }
        capabilities {
          rpc {
            type: LIST_VOLUMES
          }
        }
        capabilities {
          rpc {
            type: GET_CAPACITY
          }
        }
```

Check that the CSI *node* services are also running:

```
[vagrant@master ~]$ kubectl get pod --selector=app=csi-node
NAME             READY     STATUS    RESTARTS   AGE
csi-node-29sls   3/3       Running   0          29m
csi-node-p7r9r   3/3       Running   1          29m
```

Check the CSI *node* logs:

```
[vagrant@master ~]$ kubectl logs csi-node-29sls -c csi-driver
Starting cinderlib CSI v0.0.2 in node only mode (cinderlib: v0.2.2.dev0, cinder: v11.1.1, CSI spec: v0.2.0)
Supported filesystems are: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
Running as node
Debugging feature is ENABLED with cinderlib_csi.rpdb and OFF. Toggle it with SIGUSR1.
Now serving on unix:///csi-data/csi.sock...
=> 2018-07-24 10:14:04.339319 GRPC [123797944]: GetPluginInfo without params
<= 2018-07-24 10:14:04.339360 GRPC in 0s [123797944]: GetPluginInfo returns
        name: "com.redhat.cinderlib-csi"
        vendor_version: "0.0.2"
        manifest {
          key: "cinder-version"
          value: "11.1.1"
        }
        manifest {
          key: "cinderlib-version"
          value: "0.2.2.dev0"
        }
        manifest {
          key: "mode"
          value: "node"
        }
        manifest {
          key: "persistence"
          value: "CRDPersistence"
        }
=> 2018-07-24 10:14:04.340763 GRPC [123797584]: NodeGetId without params
<= 2018-07-24 10:14:04.340781 GRPC in 0s [123797584]: NodeGetId returns
        node_id: "node1"


[vagrant@master ~]$ kubectl logs csi-node-p7r9r -c csi-driver
Starting cinderlib CSI v0.0.2 in node only mode (cinderlib: v0.2.2.dev0, cinder: v11.1.1, CSI spec: v0.2.0)
Supported filesystems are: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
Running as node
Debugging feature is ENABLED with cinderlib_csi.rpdb and OFF. Toggle it with SIGUSR1.
Now serving on unix:///csi-data/csi.sock...
=> 2018-07-24 10:14:24.686979 GRPC [126448056]: GetPluginInfo without params
<= 2018-07-24 10:14:24.687173 GRPC in 0s [126448056]: GetPluginInfo returns
        name: "com.redhat.cinderlib-csi"
        vendor_version: "0.0.2"
        manifest {
          key: "cinder-version"
          value: "11.1.1"
        }
        manifest {
          key: "cinderlib-version"
          value: "0.2.2.dev0"
        }
        manifest {
          key: "mode"
          value: "node"
        }
        manifest {
          key: "persistence"
          value: "CRDPersistence"
        }
=> 2018-07-24 10:14:24.691020 GRPC [126447696]: NodeGetId without params
<= 2018-07-24 10:14:24.691048 GRPC in 0s [126447696]: NodeGetId returns
        node_id: "node0"
```


Check the connection information that the *node* services are storing in Kubernetes to be used by the *controller* to export and map volumes to them:

```
[vagrant@master ~]$ kubectl get keyvalue
NAME      AGE
node0     30m
node1     30m

[vagrant@master ~]$ kubectl describe kv
Name:         node0
Namespace:    default
Labels:       <none>
Annotations:  value={"platform":"x86_64","host":"node0","do_local_attach":false,"ip":"192.168.10.100","os_type":"linux2","multipath":true,"initiator":"iqn.1994
-05.com.redhat:6cf4bf7fddc0"}                                                                                                                                  API Version:  cinderlib.gorka.eguileor.com/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2018-07-24T10:14:16Z
  Generation:          1
  Resource Version:    760
  Self Link:           /apis/cinderlib.gorka.eguileor.com/v1/namespaces/default/keyvalues/node0
  UID:                 525d03cf-8f2a-11e8-847c-525400059da0
Events:                <none>


Name:         node1
Namespace:    default
Labels:       <none>
Annotations:  value={"platform":"x86_64","host":"node1","do_local_attach":false,"ip":"192.168.10.101","os_type":"linux2","multipath":true,"initiator":"iqn.1994
-05.com.redhat:1ad738f0b4e"}                                                                                                                                   API Version:  cinderlib.gorka.eguileor.com/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2018-07-24T10:14:03Z
  Generation:          1
  Resource Version:    735
  Self Link:           /apis/cinderlib.gorka.eguileor.com/v1/namespaces/default/keyvalues/node1
  UID:                 4a4481dc-8f2a-11e8-847c-525400059da0
Events:                <none>
```

Create a 1GB volume using provided PVC manifest:

```
[vagrant@master ~]$ kubectl create -f kubeyml/pvc.yml
persistentvolumeclaim/csi-pvc created
```

Check the PVC in Kubernetes, and its metadata from the CSI plugin stored in Kubernetes using CRDs:

```
$ kubectl get pvc
[vagrant@master ~]$ kubectl get pvc
NAME      STATUS    VOLUME                 CAPACITY   ACCESS MODES   STORAGECLASS   AGE
csi-pvc   Pending                                                    csi-sc         1s


[vagrant@master ~]$ kubectl get pvc
NAME      STATUS    VOLUME                 CAPACITY   ACCESS MODES   STORAGECLASS   AGE
csi-pvc   Bound     pvc-c24d470e8f2e11e8   1Gi        RWO            csi-sc         25s


[vagrant@master ~]$ kubectl get vol
NAME                                   AGE
4c1b19f4-7336-4d97-b4ab-5ea70efd39d5   1m


[vagrant@master ~]$ kubectl describe vol
Name:         4c1b19f4-7336-4d97-b4ab-5ea70efd39d5
Namespace:    default
Labels:       backend_name=lvm
              volume_id=4c1b19f4-7336-4d97-b4ab-5ea70efd39d5
              volume_name=pvc-c24d470e8f2e11e8
Annotations:  json={"ovo":{"versioned_object.version":"1.6","versioned_object.name":"Volume","versioned_object.data":{"migration_status":null,"provider_id":null,"availability_zone":"lvm","terminated_at":null,"updat...
API Version:  cinderlib.gorka.eguileor.com/v1
Kind:         Volume
Metadata:
  Creation Timestamp:  2018-07-24T10:46:02Z
  Generation:          1
  Resource Version:    3459
  Self Link:           /apis/cinderlib.gorka.eguileor.com/v1/namespaces/default/volumes/4c1b19f4-7336-4d97-b4ab-5ea70efd39d5
  UID:                 c2791ec8-8f2e-11e8-847c-525400059da0
Events:                <none>
```

Each one of the CSI plugin services is running the `akrog/csc` container, allowing us to easily send commands directly to CSI plugins using the [Container Storage Client](https://github.com/rexray/gocsi/tree/master/csc).

For example, we can request the CSI *controller* plugin to list volumes with:

```
[vagrant@master ~]$ kubectl exec -c csc csi-controller-0 csc controller list-volumes
"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"  1073741824
```

Now we are going to create a container on *node1*, where neither the CSI *controller* nor the LVM reside, using the `app.yml` manifest that mounts the EXT4 PVC we just created into the `/data` directory:

```
[vagrant@master ~]$ kubectl create -f kubeyml/app.yml
pod/my-csi-app created

```

Tail the CSI *controller* plugin logs to see that the plugin exports the volume:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -fc csi-driver
Starting cinderlib CSI v0.0.2 in controller only mode (cinderlib: v0.2.2.dev0, cinder: v11.1.1, CSI spec: v0.2.0)

[ . . .]

=> 2018-07-24 10:54:50.036959 GRPC [126565024]: ControllerPublishVolume with params
        volume_id: "4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"
        node_id: "node1"
        volume_capability {
          mount {
            fs_type: "ext4"
          }
          access_mode {
            mode: SINGLE_NODE_WRITER
          }
        }
        volume_attributes {
          key: "storage.kubernetes.io/csiProvisionerIdentity"
          value: "1532427201926-8081-com.redhat.cinderlib-csi"
        }
<= 2018-07-24 10:54:51.735242 GRPC in 2s [126565024]: ControllerPublishVolume returns
        publish_info {
          key: "connection_info"
          value: "{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:1ad738f0b4e\", \"ip\": \"192.168.10.101\", \"platform\": \"x86_64\", \"host\": \"node1\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": true}, \"conn\": {\"driver_volume_type\": \"iscsi\", \"data\": {\"target_luns\": [0], \"target_iqns\": [\"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\"], \"target_discovered\": false, \"encrypted\": false, \"target_iqn\": \"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_portal\": \"192.168.10.100:3260\", \"volume_id\": \"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_lun\": 0, \"auth_password\": \"xtZUGSxeoH7uQ34z\", \"auth_username\": \"DcL6r8st8MLzuVBapWhZ\", \"auth_method\": \"CHAP\", \"target_portals\": [\"192.168.10.100:3260\"]}}}"
        }
^C
```

Tail the CSI *node* plugin logs to see that the plugin actually attaches the volume to the container:

```
[vagrant@master ~]$ kubectl logs csi-node-29sls -c csi-driver
Starting cinderlib CSI v0.0.2 in node only mode (cinderlib: v0.2.2.dev0, cinder: v11.1.1, CSI spec: v0.2.0)

[ . . . ]

=> 2018-07-24 10:54:53.780587 GRPC [123798064]: NodeGetCapabilities without params
<= 2018-07-24 10:54:53.781102 GRPC in 0s [123798064]: NodeGetCapabilities returns
        capabilities {
          rpc {
            type: STAGE_UNSTAGE_VOLUME
          }
        }
=> 2018-07-24 10:54:53.784211 GRPC [123797944]: NodeStageVolume with params
        volume_id: "4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"
        publish_info {
          key: "connection_info"
          value: "{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:1ad738f0b4e\", \"ip\": \"192.168.10.101\", \"platform\": \"x86_64\", \"host\": \"node1\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": true}, \"conn\": {\"driver_volume_type\": \"iscsi\", \"data\": {\"target_luns\": [0], \"target_iqns\": [\"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\"], \"target_discovered\": false, \"encrypted\": false, \"target_iqn\": \"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_portal\": \"192.168.10.100:3260\", \"volume_id\": \"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_lun\": 0, \"auth_password\": \"xtZUGSxeoH7uQ34z\", \"auth_username\": \"DcL6r8st8MLzuVBapWhZ\", \"auth_method\": \"CHAP\", \"target_portals\": [\"192.168.10.100:3260\"]}}}"
        }
        staging_target_path: "/var/lib/kubelet/plugins/kubernetes.io/csi/pv/pvc-c24d470e8f2e11e8/globalmount"
        volume_capability {
          mount {
          }
          access_mode {
            mode: SINGLE_NODE_WRITER
          }
        }
        volume_attributes {
          key: "storage.kubernetes.io/csiProvisionerIdentity"
          value: "1532427201926-8081-com.redhat.cinderlib-csi"
        }
=> 2018-07-24 10:55:09.380330 GRPC [123799384]: NodeGetCapabilities without params
<= 2018-07-24 10:55:09.380891 GRPC in 0s [123799384]: NodeGetCapabilities returns
        capabilities {
          rpc {
            type: STAGE_UNSTAGE_VOLUME
          }
        }
=> 2018-07-24 10:55:09.383998 GRPC [123798784]: NodeStageVolume with params
        volume_id: "4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"
        publish_info {
          key: "connection_info"
          value: "{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:1ad738f0b4e\", \"ip\": \"192.168.10.101\", \"platform\": \"x86_64\", \"host\": \"node1\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": true}, \"conn\": {\"driver_volume_type\": \"iscsi\", \"data\": {\"target_luns\": [0], \"target_iqns\": [\"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\"], \"target_discovered\": false, \"encrypted\": false, \"target_iqn\": \"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_portal\": \"192.168.10.100:3260\", \"volume_id\": \"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_lun\": 0, \"auth_password\": \"xtZUGSxeoH7uQ34z\", \"auth_username\": \"DcL6r8st8MLzuVBapWhZ\", \"auth_method\": \"CHAP\", \"target_portals\": [\"192.168.10.100:3260\"]}}}"
        }
        staging_target_path: "/var/lib/kubelet/plugins/kubernetes.io/csi/pv/pvc-c24d470e8f2e11e8/globalmount"
        volume_capability {
          mount {
          }
          access_mode {
            mode: SINGLE_NODE_WRITER
          }
        }
        volume_attributes {
          key: "storage.kubernetes.io/csiProvisionerIdentity"
          value: "1532427201926-8081-com.redhat.cinderlib-csi"
        }
Retrying to get a multipathRetrying to get a multipath=> 2018-07-24 10:55:25.546019 GRPC [124162248]: NodeGetCapabilities without params
<= 2018-07-24 10:55:25.546121 GRPC in 0s [124162248]: NodeGetCapabilities returns
        capabilities {
          rpc {
            type: STAGE_UNSTAGE_VOLUME
          }
        }
=> 2018-07-24 10:55:25.557262 GRPC [123800704]: NodeStageVolume with params
        volume_id: "4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"
        publish_info {
          key: "connection_info"
          value: "{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:1ad738f0b4e\", \"ip\": \"192.168.10.101\", \"platform\": \"x86_64\", \"host\": \"node1\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": true}, \"conn\": {\"driver_volume_type\": \"iscsi\", \"data\": {\"target_luns\": [0], \"target_iqns\": [\"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\"], \"target_discovered\": false, \"encrypted\": false, \"target_iqn\": \"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_portal\": \"192.168.10.100:3260\", \"volume_id\": \"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_lun\": 0, \"auth_password\": \"xtZUGSxeoH7uQ34z\", \"auth_username\": \"DcL6r8st8MLzuVBapWhZ\", \"auth_method\": \"CHAP\", \"target_portals\": [\"192.168.10.100:3260\"]}}}"
        }
        staging_target_path: "/var/lib/kubelet/plugins/kubernetes.io/csi/pv/pvc-c24d470e8f2e11e8/globalmount"
        volume_capability {
          mount {
          }
          access_mode {
            mode: SINGLE_NODE_WRITER
          }
        }
        volume_attributes {
          key: "storage.kubernetes.io/csiProvisionerIdentity"
          value: "1532427201926-8081-com.redhat.cinderlib-csi"
        }
Retrying to get a multipath<= 2018-07-24 10:55:34.895940 GRPC in 41s [123797944]: NodeStageVolume returns nothing
<= 2018-07-24 10:55:34.900178 GRPC in 26s [123798784]: NodeStageVolume returns nothing
<= 2018-07-24 10:55:34.903827 GRPC in 9s [123800704]: NodeStageVolume returns nothing
=> 2018-07-24 10:55:34.905635 GRPC [123801424]: NodeGetCapabilities without params
<= 2018-07-24 10:55:34.905701 GRPC in 0s [123801424]: NodeGetCapabilities returns
        capabilities {
          rpc {
            type: STAGE_UNSTAGE_VOLUME
          }
        }
=> 2018-07-24 10:55:34.909208 GRPC [123800944]: NodePublishVolume with params
        volume_id: "4c1b19f4-7336-4d97-b4ab-5ea70efd39d5"
        publish_info {
          key: "connection_info"
          value: "{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:1ad738f0b4e\", \"ip\": \"192.168.10.101\", \"platform\": \"x86_64\", \"host\": \"node1\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": true}, \"conn\": {\"driver_volume_type\": \"iscsi\", \"data\": {\"target_luns\": [0], \"target_iqns\": [\"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\"], \"target_discovered\": false, \"encrypted\": false, \"target_iqn\": \"iqn.2010-10.org.openstack:volume-4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_portal\": \"192.168.10.100:3260\", \"volume_id\": \"4c1b19f4-7336-4d97-b4ab-5ea70efd39d5\", \"target_lun\": 0, \"auth_password\": \"xtZUGSxeoH7uQ34z\", \"auth_username\": \"DcL6r8st8MLzuVBapWhZ\", \"auth_method\": \"CHAP\", \"target_portals\": [\"192.168.10.100:3260\"]}}}"
        }
        staging_target_path: "/var/lib/kubelet/plugins/kubernetes.io/csi/pv/pvc-c24d470e8f2e11e8/globalmount"
        target_path: "/var/lib/kubelet/pods/fca47cf0-8f2f-11e8-847c-525400059da0/volumes/kubernetes.io~csi/pvc-c24d470e8f2e11e8/mount"
        volume_capability {
          mount {
          }
          access_mode {
            mode: SINGLE_NODE_WRITER
          }
        }
        volume_attributes {
          key: "storage.kubernetes.io/csiProvisionerIdentity"
          value: "1532427201926-8081-com.redhat.cinderlib-csi"
        }
<= 2018-07-24 10:55:34.995042 GRPC in 0s [123800944]: NodePublishVolume returns nothing
^C
```

Check that the pod has been successfully created:

```
[vagrant@master ~]$ kubectl get pod my-csi-app
NAME         READY     STATUS    RESTARTS   AGE
my-csi-app   1/1       Running   0          7m
```

We can check the connection information the CSI plugins store on Kubernetes:

```
[vagrant@master ~]$ kubectl get conn
NAME                                   AGE
b58dceb8-e793-4b11-b5a5-aaf1ca56d9e2   7m


[vagrant@master ~]$ kubectl describe conn
Name:         b58dceb8-e793-4b11-b5a5-aaf1ca56d9e2
Namespace:    default
Labels:       connection_id=b58dceb8-e793-4b11-b5a5-aaf1ca56d9e2
              volume_id=4c1b19f4-7336-4d97-b4ab-5ea70efd39d5
Annotations:  json={"ovo":{"versioned_object.version":"1.2","versioned_object.name":"VolumeAttachment","versioned_object.data":{"instance_uuid":null,"detach_time":null,"attach_time":null,"connection_info":{"connect...
API Version:  cinderlib.gorka.eguileor.com/v1
Kind:         Connection
Metadata:
  Creation Timestamp:  2018-07-24T10:54:51Z
  Generation:          1
  Resource Version:    4284
  Self Link:           /apis/cinderlib.gorka.eguileor.com/v1/namespaces/default/connections/b58dceb8-e793-4b11-b5a5-aaf1ca56d9e2
  UID:                 fdb065e5-8f2f-11e8-847c-525400059da0
Events:                <none>
```

Get all the cinderlib-CSI related metadata:

```
[vagrant@master ~]$ kubectl get cinderlib
NAME      AGE
node0     49m
node1     49m

NAME                                   AGE
4c1b19f4-7336-4d97-b4ab-5ea70efd39d5   17m

NAME                                   AGE
b58dceb8-e793-4b11-b5a5-aaf1ca56d9e2   8m
```

Remember that, for debuggin purposes, besides the logs, you can also get a Python console on GRPC requests by starting the debug mode, then executing bash into the node, installing `nmap-ncat`, and when a request is made connecting to port 4444.  For example, to toggle debug mode on the controller node:


```
$ kubectl exec csi-controller-0 -c csi-driver -- kill -USR1 1
```
