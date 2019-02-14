# Kubernetes example

This is a demo for Ember-CSI as a CSI v1 plugin, deployed in Kubernetes 1.13, to showcase all its functionality: volume creation and deletion, creating snapshots and volumes from them, topology, liveness probes, etc.

It deploys a scenario where we have segregated an infra node from the 2 workload nodes, and the 2 CSI plugins are deployed on the infra node.

The 2 Ember-CSI plugins deployed are LVM iSCSI and Ceph RBD, and to illustrate the topology feature the LVM iSCSI backend is only accessible by workload *node0*, whereas the Ceph RBD backend is accessible from all workload nodes and is set as the default storage class.

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

Running the demo with the default LVM and RBD storage backends requires no configuration changes.

If we want to use a different storage backend we need to edit the `kubeyml/lvm/01-controller.yml` or `kubeyml/rbd/01-controller.yml` file to change the storage configuration for the CSI plugin. This is done by changing the *value* of the `X_CSI_BACKEND_CONFIG` environmental variable with our own driver configuration.  For more information on the specific driver configuration please refer to the [cinderlib documentation](https://cinderlib.readthedocs.io), specifically to the [Backend section](https://cinderlib.readthedocs.io/en/latest/topics/backends.html), and the [Validated drivers' section](https://cinderlib.readthedocs.io/en/latest/validated_backends.html).

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
master                     : ok=64   changed=52   unreachable=0    failed=0
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
master                     : ok=64   changed=52   unreachable=0    failed=0
node0                      : ok=22   changed=20   unreachable=0    failed=0
node1                      : ok=22   changed=20   unreachable=0    failed=0
```


## Development Setup

If we are doing development, or if we want to test our own Ember-CSI images, we can use our own registry.  This would be the case if we have added a driver dependency,

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
NAME     STATUS   ROLES    AGE   VERSION
master   Ready    master   10m   v1.13.2
node0    Ready    <none>   10m   v1.13.2
node1    Ready    <none>   10m   v1.13.2
```

Or we can just SSH into the master and run commands in there:
```
$ vagrant ssh master
Last login: Tue Jul 24 10:12:40 2018 from 192.168.121.1
[vagrant@master ~]$ kubectl get nodes
NAME     STATUS   ROLES    AGE   VERSION
master   Ready    master   10m   v1.13.2
node0    Ready    <none>   10m   v1.13.2
node1    Ready    <none>   10m   v1.13.2
```

Unless stated otherwise, all the following commands are run assuming we are in the *master* node.

We can check that the CSI *controller* services are running in master and that they have been registered in Kubernetes as `CSIDrivers.csi.storage.k8s.io` objects:

```
[vagrant@master ~]$ kubectl get pod csi-controller-0 csi-rbd-0
[vagrant@master ~]$ kubectl get pod csi-controller-0 csi-rbd-0
NAME               READY   STATUS    RESTARTS   AGE
csi-controller-0   6/6     Running   0          8m50s
NAME               READY   STATUS    RESTARTS   AGE
csi-rbd-0          7/7     Running   1          4m12s


[vagrant@master ~]$ kubectl describe pod csi-controller-0 csi-rbd-0 |grep Node:
Node:               master/192.168.10.90
Node:               master/192.168.10.90


[vagrant@master ~]$ kubectl get csidrivers
NAME               AGE
io.ember-csi       8m
io.ember-csi.rbd   4m
```

Check the logs of the CSI *controller* to see that its running as expected:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -c csi-driver
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Running as controller with backend LVMVolumeDriver v3.0.0
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287040280] => GRPC GetPluginInfo
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287040280] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287039920] => GRPC Probe
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287039920] <= GRPC Probe served in 0s
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287040400] => GRPC ControllerGetCapabilities
2019-02-14 14:17:03 INFO ember_csi.common [req-140148287040400] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040280] => GRPC GetPluginInfo
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040280] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287039920] => GRPC Probe
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287039920] <= GRPC Probe served in 0s
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040400] => GRPC GetPluginInfo
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040400] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040280] => GRPC GetPluginCapabilities
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287040280] <= GRPC GetPluginCapabilities served in 0s
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287039920] => GRPC ControllerGetCapabilities
2019-02-14 14:17:04 INFO ember_csi.common [req-140148287039920] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:19:49 INFO ember_csi.common [req-140148287040400] => GRPC Probe
2019-02-14 14:19:49 INFO ember_csi.common [req-140148287040400] <= GRPC Probe served in 0s
2019-02-14 14:21:19 INFO ember_csi.common [req-140148287040400] => GRPC Probe
2019-02-14 14:21:19 INFO ember_csi.common [req-140148287040400] <= GRPC Probe served in 0s
2019-02-14 14:22:49 INFO ember_csi.common [req-140148287033424] => GRPC Probe
2019-02-14 14:22:49 INFO ember_csi.common [req-140148287033424] <= GRPC Probe served in 0s
2019-02-14 14:24:19 INFO ember_csi.common [req-140148287034624] => GRPC Probe
2019-02-14 14:24:19 INFO ember_csi.common [req-140148287034624] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-rbd-0 -c csi-driver
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Running as controller with backend RBDDriver v1.2.0
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:21:15 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] => GRPC GetPluginInfo
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] => GRPC GetPluginInfo
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625328] => GRPC Probe
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625328] <= GRPC Probe served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] => GRPC ControllerGetCapabilities
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] => GRPC Probe
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] <= GRPC Probe served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625328] => GRPC GetPluginInfo
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625328] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] => GRPC GetPluginCapabilities
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198625208] <= GRPC GetPluginCapabilities served in 0s
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] => GRPC ControllerGetCapabilities
2019-02-14 14:21:16 INFO ember_csi.common [req-140121198624848] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:24:11 INFO ember_csi.common [req-140121198625328] => GRPC Probe
2019-02-14 14:24:11 INFO ember_csi.common [req-140121198625328] <= GRPC Probe served in 0s
2019-02-14 14:25:41 INFO ember_csi.common [req-140121198625208] => GRPC Probe
2019-02-14 14:25:41 INFO ember_csi.common [req-140121198625208] <= GRPC Probe served in 0s
```

Check that the CSI *node* services are also running:

```
[vagrant@master ~]$ kubectl get pod --selector=app=csi-node
NAME               READY   STATUS    RESTARTS   AGE
csi-node-0-jpdsg   3/3     Running   1          11m
csi-node-qf4ld     3/3     Running   1          11m

[vagrant@master ~]$ kubectl get pod --selector=app=csi-node-rbd
NAME                 READY   STATUS    RESTARTS   AGE
csi-node-rbd-k5dx5   3/3     Running   0          8m38s
csi-node-rbd-mrxwc   3/3     Running   0          8m38s
```

We can also check all CSI drivers that have been registered in Kubernetes as `CSINodeInfo.csi.storage.k8s.io` objects and that both plugins have added their topology keys:

```
[vagrant@master ~]$ kubectl get csinodeinfo
NAME    AGE
node0   13m
node1   13m


vagrant@master ~]$ kubectl describe csinodeinfo
Name:         node0
Namespace:
Labels:       <none>
Annotations:  <none>
API Version:  csi.storage.k8s.io/v1alpha1
Kind:         CSINodeInfo
Metadata:
  Creation Timestamp:  2019-02-14T14:18:47Z
  Generation:          3
  Owner References:
    API Version:     v1
    Kind:            Node
    Name:            node0
    UID:             b9cc0120-3062-11e9-b3b0-5254002dbb88
  Resource Version:  1333
  Self Link:         /apis/csi.storage.k8s.io/v1alpha1/csinodeinfos/node0
  UID:               717b2f2e-3063-11e9-aed5-5254002dbb88
Spec:
  Drivers:
    Name:     io.ember-csi
    Node ID:  io.ember-csi.node0
    Topology Keys:
      iscsi
    Name:     io.ember-csi.rbd
    Node ID:  io.ember-csi.rbd.node0
    Topology Keys:
      rbd
Status:
  Drivers:
    Available:                true
    Name:                     io.ember-csi
    Volume Plugin Mechanism:  in-tree
    Available:                true
    Name:                     io.ember-csi.rbd
    Volume Plugin Mechanism:  in-tree
Events:                       <none>


Name:         node1
Namespace:
Labels:       <none>
Annotations:  <none>
API Version:  csi.storage.k8s.io/v1alpha1
Kind:         CSINodeInfo
Metadata:
  Creation Timestamp:  2019-02-14T14:18:48Z
  Generation:          3
  Owner References:
    API Version:     v1
    Kind:            Node
    Name:            node1
    UID:             b9ead21f-3062-11e9-b3b0-5254002dbb88
  Resource Version:  1336
  Self Link:         /apis/csi.storage.k8s.io/v1alpha1/csinodeinfos/node1
  UID:               71c5bc98-3063-11e9-aed5-5254002dbb88
Spec:
  Drivers:
    Name:     io.ember-csi
    Node ID:  io.ember-csi.node1
    Topology Keys:
      iscsi
    Name:     io.ember-csi.rbd
    Node ID:  io.ember-csi.rbd.node1
    Topology Keys:
      rbd
Status:
  Drivers:
    Available:                true
    Name:                     io.ember-csi
    Volume Plugin Mechanism:  in-tree
    Available:                true
    Name:                     io.ember-csi.rbd
    Volume Plugin Mechanism:  in-tree
Events:                       <none>
```

Check the CSI *node* logs:

```
[vagrant@master ~]$ kubectl logs csi-node-0-jpdsg -c csi-driver
2019-02-14 14:18:41 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:18:47 INFO ember_csi.common [req-139625352109064] => GRPC GetPluginInfo
2019-02-14 14:18:47 INFO ember_csi.common [req-139625352109064] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:18:47 INFO ember_csi.common [req-139625352108584] => GRPC NodeGetInfo
2019-02-14 14:18:47 INFO ember_csi.common [req-139625352108584] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:21:07 INFO ember_csi.common [req-139625352107984] => GRPC Probe
2019-02-14 14:21:07 INFO ember_csi.common [req-139625352107984] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-qf4ld -c csi-driver
2019-02-14 14:18:42 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:18:48 INFO ember_csi.common [req-140458013056008] => GRPC GetPluginInfo
2019-02-14 14:18:48 INFO ember_csi.common [req-140458013056008] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:18:48 INFO ember_csi.common [req-140458013055528] => GRPC NodeGetInfo
2019-02-14 14:18:48 INFO ember_csi.common [req-140458013055528] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:22:05 INFO ember_csi.common [req-140458013054928] => GRPC Probe
2019-02-14 14:22:05 INFO ember_csi.common [req-140458013054928] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-rbd-k5dx5 -c csi-driver
2019-02-14 14:20:45 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:20:45 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:20:45 INFO ember_csi.common [req-140165654412296] => GRPC GetPluginInfo
2019-02-14 14:20:45 INFO ember_csi.common [req-140165654412296] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:20:45 INFO ember_csi.common [req-140165654411816] => GRPC NodeGetInfo
2019-02-14 14:20:45 INFO ember_csi.common [req-140165654411816] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:23:25 INFO ember_csi.common [req-140165654411216] => GRPC Probe
2019-02-14 14:23:25 INFO ember_csi.common [req-140165654411216] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-rbd-mrxwc -c csi-driver
2019-02-14 14:20:46 WARNING os_brick.initiator.connectors.nvme [-] Unable to locate dmidecode. For Cinder RSD Backend, please make sure it is installed: [Errno 2] No such file or directory
Command: dmidecode
Exit code: -
Stdout: None
Stderr: None: ProcessExecutionError: [Errno 2] No such file or directory
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:20:46 INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:20:47 INFO ember_csi.common [req-140135792684040] => GRPC GetPluginInfo
2019-02-14 14:20:47 INFO ember_csi.common [req-140135792684040] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:20:47 INFO ember_csi.common [req-140135792683560] => GRPC NodeGetInfo
2019-02-14 14:20:47 INFO ember_csi.common [req-140135792683560] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:22:48 INFO ember_csi.common [req-140135792682960] => GRPC Probe
2019-02-14 14:22:48 INFO ember_csi.common [req-140135792682960] <= GRPC Probe served in 0s
```


Check the connection information that the Ember-CSI *node* services are storing in Kubernetes CRD objects to be used by the *controller* to export and map volumes to them:

```
[vagrant@master ~]$ kubectl get keyvalue
NAME                     AGE
io.ember-csi.node0       20m
io.ember-csi.node1       20m
io.ember-csi.rbd.node0   18m
io.ember-csi.rbd.node1   18m


[vagrant@master ~]$ kubectl describe keyvalue
Name:         io.ember-csi.node0
Namespace:    default
Labels:       <none>
Annotations:  value:
                {"platform":"x86_64","host":"node0","do_local_attach":false,"ip":"192.168.10.100","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-02-14T14:18:45Z
  Generation:          1
  Resource Version:    1064
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/io.ember-csi.node0
  UID:                 70332e8d-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         io.ember-csi.node1
Namespace:    default
Labels:       <none>
Annotations:  value:
                {"platform":"x86_64","host":"node1","do_local_attach":false,"ip":"192.168.10.101","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-02-14T14:18:45Z
  Generation:          1
  Resource Version:    1065
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/io.ember-csi.node1
  UID:                 7033259c-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         io.ember-csi.rbd.node0
Namespace:    default
Labels:       <none>
Annotations:  value:
                {"platform":"x86_64","host":"node0","do_local_attach":false,"ip":"192.168.10.100","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-02-14T14:20:45Z
  Generation:          1
  Resource Version:    1330
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/io.ember-csi.rbd.node0
  UID:                 b7ef3ad5-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         io.ember-csi.rbd.node1
Namespace:    default
Labels:       <none>
Annotations:  value:
                {"platform":"x86_64","host":"node1","do_local_attach":false,"ip":"192.168.10.101","os_type":"linux2","multipath":false,"initiator":"iqn.19...
API Version:  ember-csi.io/v1
Kind:         KeyValue
Metadata:
  Creation Timestamp:  2019-02-14T14:20:46Z
  Generation:          1
  Resource Version:    1334
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/io.ember-csi.rbd.node1
  UID:                 b8517e9f-3063-11e9-aed5-5254002dbb88
Events:                <none>
```

Create a 1GB volume on the LVM backend using provided PVC manifest:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/05-pvc.yml
persistentvolumeclaim/csi-pvc created
```

Check the PVC an PVs in Kubernetes, and see that the PV has Node Affinity based on the topology indicating it needs to be in a node with iSCSI (not *node0*):

```
[vagrant@master ~]$ kubectl get pvc
NAME      STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
csi-pvc   Bound    pvc-7db8685b-3066-11e9-aed5-5254002dbb88   1Gi        RWO            csi-sc         9s


[vagrant@master ~]$ kubectl get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM             STORAGECLASS   REASON   AGE
pvc-7db8685b-3066-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/csi-pvc   csi-sc                  14s


[vagrant@master ~]$ kubectl describe pv
Name:              pvc-7db8685b-3066-11e9-aed5-5254002dbb88
Labels:            <none>
Annotations:       pv.kubernetes.io/provisioned-by: io.ember-csi
Finalizers:        [kubernetes.io/pv-protection]
StorageClass:      csi-sc
Status:            Bound
Claim:             default/csi-pvc
Reclaim Policy:    Delete
Access Modes:      RWO
VolumeMode:        Filesystem
Capacity:          1Gi
Node Affinity:
  Required Terms:
    Term 0:        iscsi in [true]
Message:
Source:
    Type:              CSI (a Container Storage Interface (CSI) volume source)
    Driver:            io.ember-csi
    VolumeHandle:      540c5a37-ce98-4b47-83f7-10c54a4777b9
    ReadOnly:          false
    VolumeAttributes:      storage.kubernetes.io/csiProvisionerIdentity=1550153767135-8081-io.ember-csi
Events:                <none>
```

We can also check Ember-CSI metadata for the volume stored in Kubernetes using CRDs:

```
[vagrant@master ~]$ kubectl get vol
NAME                                   AGE
540c5a37-ce98-4b47-83f7-10c54a4777b9   20s


[vagrant@master ~]$ kubectl describe vol
Name:         540c5a37-ce98-4b47-83f7-10c54a4777b9
Namespace:    default
Labels:       backend_name=lvm
              volume_id=540c5a37-ce98-4b47-83f7-10c54a4777b9
              volume_name=pvc-7db8685b-3066-11e9-aed5-5254002dbb88
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.8","versioned_object.name":"Volume","versioned_object.data":{"migration_status":null,"provider_id":n...
API Version:  ember-csi.io/v1
Kind:         Volume
Metadata:
  Creation Timestamp:  2019-02-14T14:40:37Z
  Generation:          1
  Resource Version:    3012
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/volumes/540c5a37-ce98-4b47-83f7-10c54a4777b9
  UID:                 7e07ab73-3066-11e9-aed5-5254002dbb88
Events:                <none>
```

Each one of the CSI pods is running the `embercsi/csc` container, allowing us to easily send CSI commands directly to the Ember-CSI service running in a pod using the [Container Storage Client](https://github.com/rexray/gocsi/tree/master/csc).

For example, we can request the LVM CSI *controller* plugin to list volumes with:

```
[vagrant@master ~]$ kubectl exec -c csc csi-controller-0 csc controller list-volumes
"540c5a37-ce98-4b47-83f7-10c54a4777b9"  1073741824
```

Now we are going to create a pod/container that uses the PV/PVC we created earlier, and since this PV is restricted to a node with the topology `iscsi=true` then it cannot go to *node0*, so it will land on *node1*.  We do this using the `06-app.yml` manifest that mounts the EXT4 PVC we just created into the `/data` directory:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/06-app.yml
pod/my-csi-app created

```

Tail the CSI *controller* plugin logs to see that the plugin exports the volume:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -fc csi-driver
2019-02-14 14:17:03 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)


[ . . .]

2019-02-14 14:52:49 INFO ember_csi.common [req-140148287036904] => GRPC Probe
2019-02-14 14:52:49 INFO ember_csi.common [req-140148287036904] <= GRPC Probe served in 0s
2019-02-14 14:53:29 INFO ember_csi.common [req-140148287037024] => GRPC ControllerPublishVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:31 INFO ember_csi.common [req-140148287037024] <= GRPC ControllerPublishVolume served in 2s
^C
```

Tail the CSI *node* plugin logs to see that the plugin actually attaches the volume to the container:

```
[vagrant@master ~]$ kubectl logs csi-node-qf4ld -fc csi-driver
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)

[ . . . ]

2019-02-14 14:53:44 INFO ember_csi.common [req-140458012850128] => GRPC Probe
2019-02-14 14:53:44 INFO ember_csi.common [req-140458012850128] <= GRPC Probe served in 0s
2019-02-14 14:53:45 INFO ember_csi.common [req-140458012850248] => GRPC NodeGetCapabilities
2019-02-14 14:53:45 INFO ember_csi.common [req-140458012850248] <= GRPC NodeGetCapabilities served in 0s
2019-02-14 14:53:45 INFO ember_csi.common [req-140458012850368] => GRPC NodeStageVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:47 WARNING os_brick.initiator.connectors.iscsi [req-140458012850368] iscsiadm stderr output when getting sessions: iscsiadm: No active sessions.

2019-02-14 14:53:50 INFO ember_csi.common [req-140458012850368] <= GRPC NodeStageVolume served in 5s
2019-02-14 14:53:50 INFO ember_csi.common [req-140458012850488] => GRPC NodeGetCapabilities
2019-02-14 14:53:50 INFO ember_csi.common [req-140458012850488] <= GRPC NodeGetCapabilities served in 0s
2019-02-14 14:53:50 INFO ember_csi.common [req-140458012850248] => GRPC NodePublishVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:50 INFO ember_csi.common [req-140458012850248] <= GRPC NodePublishVolume served in 0s
2019-02-14 14:55:05 INFO ember_csi.common [req-140458012850608] => GRPC Probe
2019-02-14 14:55:05 INFO ember_csi.common [req-140458012850608] <= GRPC Probe served in 0s
^C
```

Check that the pod has been successfully created and that we have the Kubernetes `VolumeAttachment` object:

```
[vagrant@master ~]$ kubectl get pod my-csi-app
NAME         READY   STATUS    RESTARTS   AGE
my-csi-app   1/1     Running   0          3m16s

[vagrant@master ~]$ kubectl get VolumeAttachment
NAME                                                                   CREATED AT
csi-ce6d09a1af97cc903bd51ef4ab34acdf6b4d5c29b763d490de4953552c9e1055   2019-02-14T14:53:29Z
```

We can check the Ember-CSI connection metadata stored on Kubernetes as CRD objects:

```
[vagrant@master ~]$ kubectl get conn
NAME                                   AGE
63394bf4-9153-4c9c-9e76-aa73d5b80b48   5m


[vagrant@master ~]$ kubectl describe conn
Name:         63394bf4-9153-4c9c-9e76-aa73d5b80b48
Namespace:    default
Labels:       connection_id=63394bf4-9153-4c9c-9e76-aa73d5b80b48
              volume_id=540c5a37-ce98-4b47-83f7-10c54a4777b9
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.3","versioned_object.name":"VolumeAttachment","versioned_object.data":{"instance_uuid":null,"detach_...
API Version:  ember-csi.io/v1
Kind:         Connection
Metadata:
  Creation Timestamp:  2019-02-14T14:53:31Z
  Generation:          1
  Resource Version:    4141
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/connections/63394bf4-9153-4c9c-9e76-aa73d5b80b48
  UID:                 4bbed677-3068-11e9-aed5-5254002dbb88
Events:                <none>
```

Now let's create a snapshot of our volume, and see its Kubernetes and Ember-CSI representations:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/07-snapshot.yml
volumesnapshot.snapshot.storage.k8s.io/csi-snap created


[vagrant@master ~]$ kubectl describe VolumeSnapshot
Name:         csi-snap
Namespace:    default
Labels:       <none>
Annotations:  <none>
API Version:  snapshot.storage.k8s.io/v1alpha1
Kind:         VolumeSnapshot
Metadata:
  Creation Timestamp:  2019-02-14T15:00:35Z
  Finalizers:
    snapshot.storage.kubernetes.io/volumesnapshot-protection
  Generation:        5
  Resource Version:  4723
  Self Link:         /apis/snapshot.storage.k8s.io/v1alpha1/namespaces/default/volumesnapshots/csi-snap
  UID:               488d1760-3069-11e9-aed5-5254002dbb88
Spec:
  Snapshot Class Name:    csi-snap
  Snapshot Content Name:  snapcontent-488d1760-3069-11e9-aed5-5254002dbb88
  Source:
    API Group:  <nil>
    Kind:       PersistentVolumeClaim
    Name:       csi-pvc
Status:
  Creation Time:  2019-02-14T15:00:35Z
  Ready To Use:   true
  Restore Size:   <nil>
Events:           <none>


[vagrant@master ~]$ kubectl describe snap
Name:         2cee62a1-6ad9-4554-8c58-f5d3dd07525f
Namespace:    default
Labels:       snapshot_id=2cee62a1-6ad9-4554-8c58-f5d3dd07525f
              snapshot_name=snapshot-488d1760-3069-11e9-aed5-5254002dbb88
              volume_id=540c5a37-ce98-4b47-83f7-10c54a4777b9
Annotations:  json:
                {"ovo":{"versioned_object.version":"1.5","versioned_object.name":"Snapshot","versioned_object.data":{"provider_id":null,"updated_at":null,...
API Version:  ember-csi.io/v1
Kind:         Snapshot
Metadata:
  Creation Timestamp:  2019-02-14T15:00:36Z
  Generation:          1
  Resource Version:    4718
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/snapshots/2cee62a1-6ad9-4554-8c58-f5d3dd07525f
  UID:                 48e7db9b-3069-11e9-aed5-5254002dbb88
Events:                <none>
```

Now create a volume from that snapshot:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/08-restore-snapshot.yml
persistentvolumeclaim/vol-from-snap created


[vagrant@master ~]$ kubectl get vol
NAME                                   AGE
540c5a37-ce98-4b47-83f7-10c54a4777b9   21m
faa72ced-43ef-45ac-9bfe-5781e15f75da   6s
```

And create another pod/container using this new volume, which will be subject to the same topology restrictions as our first volume, so it will also be created on *node1*.

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/09-app-from-snap-vol.yml
pod/my-csi-app-2 created

[vagrant@master ~]$ kubectl describe pod my-csi-app-2 |grep Node:
Node:               node1/192.168.10.101

[vagrant@master ~]$ kubectl get conn
NAME                                   AGE
35c43fc6-65db-4ce5-b328-830c86eba08a   40s
63394bf4-9153-4c9c-9e76-aa73d5b80b48   10m

[vagrant@master ~]$ kubectl get pod
NAME                 READY   STATUS    RESTARTS   AGE
csi-controller-0     6/6     Running   0          48m
csi-node-0-jpdsg     3/3     Running   1          46m
csi-node-qf4ld       3/3     Running   1          46m
csi-node-rbd-k5dx5   3/3     Running   0          43m
csi-node-rbd-mrxwc   3/3     Running   0          43m
csi-rbd-0            7/7     Running   1          43m
my-csi-app           1/1     Running   0          10m
my-csi-app-2         1/1     Running   0          55s
```

We can now all these same steps with the RBD backend that, according to the topology we've defined, can be accessed from all of our worker nodes:

```
[vagrant@master ~]$ kubectl create -f kubeyml/rbd/05-pvc.yml
persistentvolumeclaim/csi-rbd created


[vagrant@master ~]$ kubectl get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                   STORAGECLASS   REASON   AGE
pvc-7537f440-3069-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/vol-from-snap   csi-sc                  2m59s
pvc-7db8685b-3066-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/csi-pvc         csi-sc                  24m
pvc-ddf984b7-3069-11e9-aed5-5254002dbb88   2Gi        RWO            Delete           Bound    default/csi-rbd         csi-rbd                 3s


[vagrant@master ~]$ kubectl create -f kubeyml/rbd/06-app.yml
pod/my-csi-app-rbd created


[vagrant@master ~]$ kubectl create -f kubeyml/rbd/07-snapshot.yml
volumesnapshot.snapshot.storage.k8s.io/csi-rbd created


[vagrant@master ~]$ kubectl get snap
NAME                                   AGE
2cee62a1-6ad9-4554-8c58-f5d3dd07525f   5m
79fd2dff-7ba5-4e29-b4b4-64ee94e1c36d   14s


[vagrant@master ~]$ kubectl create -f kubeyml/rbd/08-restore-snapshot.yml
persistentvolumeclaim/vol-from-snap-rbd created


[vagrant@master ~]$ kugetctl get pv
-bash: kugetctl: command not found
[vagrant@master ~]$ kubectl get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                       STORAGECLASS   REASON   AGE
pvc-1117b711-306a-11e9-aed5-5254002dbb88   2Gi        RWO            Delete           Bound    default/vol-from-snap-rbd   csi-rbd                 11s
pvc-7537f440-3069-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/vol-from-snap       csi-sc                  4m31s
pvc-7db8685b-3066-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/csi-pvc             csi-sc                  25m
pvc-ddf984b7-3069-11e9-aed5-5254002dbb88   2Gi        RWO            Delete           Bound    default/csi-rbd             csi-rbd                 95s


[vagrant@master ~]$ kubectl create -f kubeyml/rbd/09-app-from-snap-vol.yml
pod/my-csi-app-rbd-2 created

[vagrant@master ~]$ kubectl get pod
NAME                 READY   STATUS    RESTARTS   AGE
csi-controller-0     6/6     Running   0          52m
csi-node-0-jpdsg     3/3     Running   1          50m
csi-node-qf4ld       3/3     Running   1          50m
csi-node-rbd-k5dx5   3/3     Running   0          47m
csi-node-rbd-mrxwc   3/3     Running   0          47m
csi-rbd-0            7/7     Running   1          47m
my-csi-app           1/1     Running   0          14m
my-csi-app-2         1/1     Running   0          4m54s
my-csi-app-rbd       1/1     Running   0          3m1s
my-csi-app-rbd-2     1/1     Running   0          84s

[vagrant@master ~]$ kubectl describe pod my-csi-app-rbd |grep Node:
Node:               node0/192.168.10.100


[vagrant@master ~]$ kubectl describe pod my-csi-app-rbd-2 |grep Node:
Node:               node1/192.168.10.101
```

All the internal Ember-CSI metadata is grouped under the name `ember`, and we can get it all like this:

```
[vagrant@master ~]$ kubectl get ember
NAME                                                         AGE
snapshot.ember-csi.io/2cee62a1-6ad9-4554-8c58-f5d3dd07525f   9m
snapshot.ember-csi.io/79fd2dff-7ba5-4e29-b4b4-64ee94e1c36d   4m

NAME                                                           AGE
connection.ember-csi.io/35c43fc6-65db-4ce5-b328-830c86eba08a   6m
connection.ember-csi.io/63394bf4-9153-4c9c-9e76-aa73d5b80b48   16m
connection.ember-csi.io/a96e8e33-f14e-46e6-8732-67efae593539   5m
connection.ember-csi.io/eeb85633-a554-4b2d-aabe-a8bf5c3b7f41   3m

NAME                                                       AGE
volume.ember-csi.io/540c5a37-ce98-4b47-83f7-10c54a4777b9   29m
volume.ember-csi.io/9e1e7f95-2007-4775-92a8-896881b22618   3m
volume.ember-csi.io/f91e729e-e9d1-4a28-89f8-293423047eea   5m
volume.ember-csi.io/faa72ced-43ef-45ac-9bfe-5781e15f75da   8m

NAME                                           AGE
keyvalue.ember-csi.io/io.ember-csi.node0       51m
keyvalue.ember-csi.io/io.ember-csi.node1       51m
keyvalue.ember-csi.io/io.ember-csi.rbd.node0   49m
keyvalue.ember-csi.io/io.ember-csi.rbd.node1   49m
```


Remember that, for debugging purposes, besides the logs, you can also get a Python console on GRPC requests by starting the debug mode, then executing bash into the node, installing `nmap-ncat`, and when a request is made connecting to port 4444.  For example, to toggle debug mode on the controller node:


```
$ kubectl exec csi-controller-0 -c csi-driver -- kill -USR1 1
```
