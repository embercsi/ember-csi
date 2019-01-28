
ADD

 kubectl get csinodeinfo.csi.storage.k8s.io  --> Works


Fails:
kubectl get csidrivers.csi.storage.k8s.io


# Kubernetes setup

This demo deploys a Kubernetes single CentOS 7 master cluster, as the infra node, with 2 additional nodes, as workload nodes, using [kubeadm](http://kubernetes.io/docs/admin/kubeadm/) and Ember-CSI as the storage provider running v1.0 of the CSI spec with an LVM loopback device as the backend.

CSI driver is set as the default storage class, running 1 service (`StatefulSet`) with the CSI plugin running as *Controller* to manage the provisioning on *master*, as part of the infrastructure, and a service (`DaemonSet`) running the plugin as *Node* mode on each of the nodes to manage local attachments.

This example uses Vagrant, libvirt, KVM, and Ansible to create and provision these 3 VMs.

**These Ansible playbooks are not idempotent, so don't run them more than once**

This demo is based on Luis Pabon's [Kubeup repository](https://github.com/lpabon/kubeup).

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
master                     : ok=55   changed=44   unreachable=0    failed=0
node0                      : ok=22   changed=20   unreachable=0    failed=0
node1                      : ok=22   changed=20   unreachable=0    failed=0
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
master                     : ok=55   changed=44   unreachable=0    failed=0
node0                      : ok=22   changed=20   unreachable=0    failed=0
node1                      : ok=22   changed=20   unreachable=0    failed=0
```


## Development Setup

If we are doing development, or if we want to test our own Ember-CSI images, for example if we have added a driver dependency, we can use our own registry.

Here's an example of what we would do to test a 3PAR iSCSI backend, which has dependencies that are not currently included in any of the Ember-CSI images:

First we would create our docker image, with a `Dockerfile` such as this:

```
FROM embercsi/ember-csi:master
RUN pip install 'python-3parclient>=4.1.0'
```

Then we build and tag the image with our IP address:

```
# We need to know our IP address
$ MY_IP=$(bash -c 'a="`hostname -I`"; s=($a); echo ${s[0]}')
$ docker build -t $MY_IP/ember-csi:testing .
```

Now we run our own registry and publish our image:

```
$ docker run -d -p 5000:5000 --name registry registry:2
$ docker push -t $MY_IP:5000/ember-csi:testing
```

Then, we edit file `roles/common/files/daemon.json` and replace the IP with our own, so that docker can pull images from our insecure registry, and change the images we want to use:

```
$ sed -i "s/192.168.1.11:5000/$MY_IP:5000/" roles/common/files/daemon.json
$ sed -i "s/embercsi\/ember-csi:master/$MY_IP:5000\/ember-csi:testing/" kubeyml/node.yml
$ sed -i "s/embercsi\/ember-csi:master/$MY_IP:5000\/ember-csi:testing/" kubeyml/controller.yml
```

With that, we are now ready to use our own custom image when deploying Ember-CSI in this example, but since we wanted to use the 3PAR backend we have to change the configuration editing `kubeyml/controller.yml` and changing the value of the environmental vairiable `X_CSI_BACKEND_CONFIG` with our backend's configuration.


## Usage

After the setup is completed the Kubernetes configuration is copied from the master node to the host, so we can use it locally as follows:

```
$ kubectl --kubeconfig=kubeconfig.conf get nodes
master    Ready     master    21m       v1.13.2
node0     Ready     <none>    21m       v1.13.2
node1     Ready     <none>    21m       v1.13.2
```

Or we can just SSH into the master and run commands in there:
```
$ vagrant ssh master
Last login: Tue Jul 24 10:12:40 2018 from 192.168.121.1
[vagrant@master ~]$ kubectl get nodes
NAME      STATUS    ROLES     AGE       VERSION
master    Ready     master    21m       v1.13.2
node0     Ready     <none>    21m       v1.13.2
node1     Ready     <none>    21m       v1.13.2
```

Unless stated otherwise, all the following commands are run assuming we are in the *master* node.

We can check that the CSI *controller* service is running in master:

```
[vagrant@master ~]$ kubectl get pod csi-controller-0
NAME               READY     STATUS    RESTARTS   AGE
csi-controller-0   5/5       Running   0          22m

[vagrant@master ~]$ kubectl describe pod csi-controller-0 | grep Node:
Node:               master/192.168.10.90
```

Check the logs of the CSI *controller* to see that its running as expected:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -c csi-driver
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v13.1.0.dev731, CSI spec: v1.0.0)
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Running as controller with backend LVMVolumeDriver v3.0.0
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350928] => GRPC Probe
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350928] <= GRPC Probe served in 0s
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350568] => GRPC GetPluginInfo
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350568] <= GRPC GetPluginInfo served in 0s
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109351048] => GRPC GetPluginCapabilities
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109351048] <= GRPC GetPluginCapabilities served in 0s
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350928] => GRPC ControllerGetCapabilities
2019-01-31 16:13:18 INFO ember_csi.common [req-139778109350928] <= GRPC ControllerGetCapabilities served in 0s
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109350568] => GRPC GetPluginInfo
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109350568] <= GRPC GetPluginInfo served in 0s
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109351048] => GRPC Probe
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109351048] <= GRPC Probe served in 0s
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109350928] => GRPC ControllerGetCapabilities
2019-01-31 16:13:19 INFO ember_csi.common [req-139778109350928] <= GRPC ControllerGetCapabilities served in 0s
```

Check that the CSI *node* services are also running:

```
[vagrant@master ~]$ kubectl get pod --selector=app=csi-node
NAME             READY     STATUS    RESTARTS   AGE
csi-node-29sls   3/3       Running   0          29m
csi-node-p7r9r   3/3       Running   1          29m
```

We can also check all CSI drivers that have been registered in the system:

```
[vagrant@master ~]$ kubectl get csinodeinfo.csi.storage.k8s.io
NAME    AGE
node0   19m
node1   19m

[vagrant@master ~]$ kubectl describe csinodeinfo.csi.storage.k8s.io
Name:         node0
Namespace:
Labels:       <none>
Annotations:  <none>
API Version:  csi.storage.k8s.io/v1alpha1
Kind:         CSINodeInfo
Metadata:
  Creation Timestamp:  2019-01-31T16:16:33Z
  Generation:          2
  Owner References:
    API Version:     v1
    Kind:            Node
    Name:            node0
    UID:             782926e7-2572-11e9-ac8a-5254009990ac
  Resource Version:  1327
  Self Link:         /apis/csi.storage.k8s.io/v1alpha1/csinodeinfos/node0
  UID:               9379f5cd-2573-11e9-9fee-5254009990ac
Spec:
  Drivers:
    Name:     io.ember-csi
    Node ID:  node0
    Topology Keys:
Status:
  Drivers:
    Available:                true
    Name:                     io.ember-csi
    Volume Plugin Mechanism:  in-tree
Events:                       <none>


Name:         node1
Namespace:
Labels:       <none>
Annotations:  <none>
API Version:  csi.storage.k8s.io/v1alpha1
Kind:         CSINodeInfo
Metadata:
  Creation Timestamp:  2019-01-31T16:16:33Z
  Generation:          2
  Owner References:
    API Version:     v1
    Kind:            Node
    Name:            node1
    UID:             781c207f-2572-11e9-ac8a-5254009990ac
  Resource Version:  1317
  Self Link:         /apis/csi.storage.k8s.io/v1alpha1/csinodeinfos/node1
  UID:               9354055e-2573-11e9-9fee-5254009990ac
Spec:
  Drivers:
    Name:     io.ember-csi
    Node ID:  node1
    Topology Keys:
Status:
  Drivers:
    Available:                true
    Name:                     io.ember-csi
    Volume Plugin Mechanism:  in-tree
Events:                       <none>
```

Check the CSI *node* logs:

```
[vagrant@master ~]$ kubectl logs csi-node-29sls -c csi-driver
2019-01-31 16:16:32 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v13.1.0.dev731, CSI spec: v1.0.0)
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Running as node
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-01-31 16:16:33 INFO ember_csi.common [req-139891336430728] => GRPC GetPluginInfo
2019-01-31 16:16:33 INFO ember_csi.common [req-139891336430728] <= GRPC GetPluginInfo served in 0s
2019-01-31 16:16:33 INFO ember_csi.common [req-139891336430368] => GRPC NodeGetInfo
2019-01-31 16:16:33 INFO ember_csi.common [req-139891336430368] <= GRPC NodeGetInfo served in 0s


[vagrant@master ~]$ kubectl logs csi-node-p7r9r -c csi-driver
2019-01-31 16:16:32 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v13.1.0.dev731, CSI spec: v1.0.0)
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Running as node
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-01-31 16:16:33 INFO ember_csi.common [req-140339816875144] => GRPC GetPluginInfo
2019-01-31 16:16:33 INFO ember_csi.common [req-140339816875144] <= GRPC GetPluginInfo served in 0s
2019-01-31 16:16:33 INFO ember_csi.common [req-140339816874784] => GRPC NodeGetInfo
2019-01-31 16:16:33 INFO ember_csi.common [req-140339816874784] <= GRPC NodeGetInfo served in 0s
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
Annotations:  value:
                {"platform":"x86_64","host":"node0","do_local_attach":false,"ip":"192.168.10.100","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-01-31T16:16:32Z
  Generation:          1
  Resource Version:    1306
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/node0
  UID:                 92e46590-2573-11e9-9fee-5254009990ac
Events:                <none>


Name:         node1
Namespace:    default
Labels:       <none>
Annotations:  value:
                {"platform":"x86_64","host":"node1","do_local_attach":false,"ip":"192.168.10.101","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-01-31T16:16:32Z
  Generation:          1
  Resource Version:    1308
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/node1
  UID:                 92e6031f-2573-11e9-9fee-5254009990ac
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
NAME      STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
csi-pvc   Bound    pvc-2a286b60-2574-11e9-9fee-5254009990ac   1Gi        RWO            csi-sc         11s


[vagrant@master ~]$ kubectl get vol
NAME                                   AGE
82e9460c-cd04-4e08-94bb-7149b2805065   1m


[vagrant@master ~]$ kubectl describe vol
Name:         82e9460c-cd04-4e08-94bb-7149b2805065
Namespace:    default
Labels:       backend_name=lvm
              volume_id=82e9460c-cd04-4e08-94bb-7149b2805065
              volume_name=pvc-2a286b60-2574-11e9-9fee-5254009990ac
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.8","versioned_object.name":"Volume","versioned_object.data":{"migration_status":null,"provider_id":n...
API Version:  ember-csi.io/v1
Kind:         Volume
Metadata:
  Creation Timestamp:  2019-01-31T16:20:46Z
  Generation:          1
  Resource Version:    1690
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/volumes/82e9460c-cd04-4e08-94bb-7149b2805065
  UID:                 2a6d8a7c-2574-11e9-9fee-5254009990ac
Events:                <none>
```

Each one of the CSI plugin services is running the `embercsi/csc` container, allowing us to easily send commands directly to CSI plugins using the [Container Storage Client](https://github.com/rexray/gocsi/tree/master/csc).

For example, we can request the CSI *controller* plugin to list volumes with:

```
[vagrant@master ~]$ kubectl exec -c csc csi-controller-0 csc controller list-volumes
"82e9460c-cd04-4e08-94bb-7149b2805065"  1073741824
```

Now we are going to create a container on *node1*, where neither the CSI *controller* nor the LVM reside, using the `app.yml` manifest that mounts the EXT4 PVC we just created into the `/data` directory:

```
[vagrant@master ~]$ kubectl create -f kubeyml/app.yml
pod/my-csi-app created

```

Tail the CSI *controller* plugin logs to see that the plugin exports the volume:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -fc csi-driver
2019-01-31 16:13:18 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v13.1.0.dev731, CSI spec: v1.0.0)

[ . . .]

2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350568] => GRPC GetPluginCapabilities
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350568] <= GRPC GetPluginCapabilities served in 0s
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109351048] => GRPC ControllerGetCapabilities
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109351048] <= GRPC ControllerGetCapabilities served in 0s
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350928] => GRPC GetPluginInfo
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350928] <= GRPC GetPluginInfo served in 0s
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350568] => GRPC CreateVolume pvc-2a286b60-2574-11e9-9fee-5254009990ac
2019-01-31 16:20:46 INFO ember_csi.common [req-139778109350568] <= GRPC CreateVolume (id = 82e9460c-cd04-4e08-94bb-7149b2805065) served in 0s
2019-01-31 16:22:56 INFO ember_csi.common [req-139778109353208] => GRPC ListVolumes
2019-01-31 16:22:56 INFO ember_csi.common [req-139778109353208] <= GRPC ListVolumes served in 0s
2019-01-31 16:23:32 INFO ember_csi.common [req-139778109350928] => GRPC ControllerPublishVolume 82e9460c-cd04-4e08-94bb-7149b2805065
2019-01-31 16:23:34 INFO ember_csi.common [req-139778109350928] <= GRPC ControllerPublishVolume served in 2s
2019-01-31 16:23:34 INFO ember_csi.common [req-139778109353328] => GRPC ControllerPublishVolume 82e9460c-cd04-4e08-94bb-7149b2805065
2019-01-31 16:23:34 INFO ember_csi.common [req-139778109353328] <= GRPC ControllerPublishVolume served in 0s
^C
```

Tail the CSI *node* plugin logs to see that the plugin actually attaches the volume to the container:

```
2019-01-31 16:16:32 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v13.1.0.dev731, CSI spec: v1.0.0)

[ . . . ]

2019-01-31 16:23:40 INFO ember_csi.common [req-139891336430248] => GRPC NodeGetCapabilities
2019-01-31 16:23:40 INFO ember_csi.common [req-139891336430248] <= GRPC NodeGetCapabilities served in 0s
2019-01-31 16:23:40 INFO ember_csi.common [req-139891336430008] => GRPC NodeStageVolume 82e9460c-cd04-4e08-94bb-7149b2805065
2019-01-31 16:23:42 WARNING os_brick.initiator.connectors.iscsi [req-139891336430008] iscsiadm stderr output when getting sessions: iscsiadm: No active sessions.

2019-01-31 16:23:45 INFO ember_csi.common [req-139891336430008] <= GRPC NodeStageVolume served in 5s
2019-01-31 16:23:45 INFO ember_csi.common [req-139891336430128] => GRPC NodeGetCapabilities
2019-01-31 16:23:45 INFO ember_csi.common [req-139891336430128] <= GRPC NodeGetCapabilities served in 0s
2019-01-31 16:23:45 INFO ember_csi.common [req-139891336430248] => GRPC NodePublishVolume 82e9460c-cd04-4e08-94bb-7149b2805065
2019-01-31 16:23:45 INFO ember_csi.common [req-139891336430248] <= GRPC NodePublishVolume served in 0s

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
91c4efb1-e656-462a-9e57-721f73febdb9   7m


[vagrant@master ~]$ kubectl describe conn
Name:         91c4efb1-e656-462a-9e57-721f73febdb9
Namespace:    default
Labels:       connection_id=91c4efb1-e656-462a-9e57-721f73febdb9
              volume_id=82e9460c-cd04-4e08-94bb-7149b2805065
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.3","versioned_object.name":"VolumeAttachment","versioned_object.data":{"instance_uuid":null,"detach_...
API Version:  ember-csi.io/v1
Kind:         Connection
Metadata:
  Creation Timestamp:  2019-01-31T16:23:34Z
  Generation:          1
  Resource Version:    1957
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/connections/91c4efb1-e656-462a-9e57-721f73febdb9
  UID:                 8e79ca7f-2574-11e9-9fee-5254009990ac
Events:                <none>
```

Get all the Ember-CSI related metadata:

```
[vagrant@master ~]$ kubectl get ember
NAME                                                           AGE
connection.ember-csi.io/91c4efb1-e656-462a-9e57-721f73febdb9   3m

NAME                          AGE
keyvalue.ember-csi.io/node0   10m
keyvalue.ember-csi.io/node1   10m

NAME                                                       AGE
volume.ember-csi.io/82e9460c-cd04-4e08-94bb-7149b2805065   6m
```

Now let's create a snapshot of our volume, and see its kubernetes and ember representations:

```
[vagrant@master ~]$ kubectl create -f kubeyml/snapshot.yml
volumesnapshot.snapshot.storage.k8s.io/csi-snap created

[vagrant@master ~]$ kubectl describe VolumeSnapshot
Name:         csi-snap
Namespace:    default
Labels:       <none>
Annotations:  <none>
API Version:  snapshot.storage.k8s.io/v1alpha1
Kind:         VolumeSnapshot
Metadata:
  Creation Timestamp:  2019-01-31T16:28:46Z
  Finalizers:
    snapshot.storage.kubernetes.io/volumesnapshot-protection
  Generation:        5
  Resource Version:  2396
  Self Link:         /apis/snapshot.storage.k8s.io/v1alpha1/namespaces/default/volumesnapshots/csi-snap
  UID:               48877e0d-2575-11e9-9fee-5254009990ac
Spec:
  Snapshot Class Name:    csi-snap
  Snapshot Content Name:  snapcontent-48877e0d-2575-11e9-9fee-5254009990ac
  Source:
    API Group:  <nil>
    Kind:       PersistentVolumeClaim
    Name:       csi-pvc
Status:
  Creation Time:  2019-01-31T16:28:47Z
  Ready To Use:   true
  Restore Size:   <nil>
Events:           <none>

[vagrant@master ~]$ kubectl describe snap
Name:         e37b0fd0-b7f1-4e9d-b455-a968b5a02964
Namespace:    default
Labels:       snapshot_id=e37b0fd0-b7f1-4e9d-b455-a968b5a02964
              snapshot_name=snapshot-48877e0d-2575-11e9-9fee-5254009990ac
              volume_id=82e9460c-cd04-4e08-94bb-7149b2805065
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.5","versioned_object.name":"Snapshot","versioned_object.data":{"provider_id":null,"updated_at":null,...
API Version:  ember-csi.io/v1
Kind:         Snapshot
Metadata:
  Creation Timestamp:  2019-01-31T16:28:47Z
  Generation:          1
  Resource Version:    2391
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/snapshots/e37b0fd0-b7f1-4e9d-b455-a968b5a02964
  UID:                 48de9c16-2575-11e9-9fee-5254009990ac
Events:                <none>
```

Now create a volume from that snapshot:

```
[vagrant@master ~]$ kubectl create -f kubeyml/restore-snapshot.yml
persistentvolumeclaim/vol-from-snap created

[vagrant@master ~]$ kubectl get vol
NAME                                   AGE
0766345b-dc28-427e-9cba-d21654dd97cb   10s
82e9460c-cd04-4e08-94bb-7149b2805065   11m
```

And create another container using this new volume.

```
[vagrant@master ~]$ kubectl create -f kubeyml/app-from-snap-vol.yml
pod/my-csi-app-2 created

[vagrant@master ~]$ kubectl get conn
NAME                                   AGE
4255bc1c-b8a6-40c1-8e11-f3218379cb2e   13s
91c4efb1-e656-462a-9e57-721f73febdb9   9m

[vagrant@master ~]$ kubectl get pod
NAME               READY   STATUS    RESTARTS   AGE
csi-controller-0   5/5     Running   0          21m
csi-node-29sls     3/3     Running   0          18m
csi-node-p7r9r     3/3     Running   1          18m
my-csi-app         1/1     Running   0          10m
my-csi-app-2       1/1     Running   0          38s
```


Remember that, for debuggin purposes, besides the logs, you can also get a Python console on GRPC requests by starting the debug mode, then executing bash into the node, installing `nmap-ncat`, and when a request is made connecting to port 4444.  For example, to toggle debug mode on the controller node:


```
$ kubectl exec csi-controller-0 -c csi-driver -- kill -USR1 1
```
