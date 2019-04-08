# Kubernetes example

This is a demo for Ember-CSI as a CSI v1 plugin, deployed in Kubernetes 1.13, to showcase all its functionality: volume creation and deletion, creating snapshots and volumes from them, topology, liveness probes, etc.

It deploys a scenario where we have segregated an infra node from the 2 workload nodes, and the 2 CSI plugins are deployed on the infra node.

The 2 Ember-CSI plugins deployed are LVM iSCSI and Ceph RBD, and to illustrate the topology feature the LVM iSCSI backend is only accessible by workload *node0*, whereas the Ceph RBD backend is accessible from all workload nodes and is set as the default storage class.

This example uses Vagrant, libvirt, KVM, and Ansible to create and provision these 3 VMs.

**These Ansible playbooks are not idempotent, so don't run them more than once**

This demo is based on Luis Pabon's [Kubeup repository](https://github.com/lpabon/kubeup).

## Requirements

* Install qemu-kvm, libvirt, vagrant-libvirt and ansible.

    - Fedora

    ```
    $ sudo dnf -y install qemu-kvm libvirt vagrant-libvirt ansible
    ```

* Start libvirt service.
    - Fedora
    ```
    $ sudo systemctl start libvirtd
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

Then, we edit file `global_vars.yml` and replace the IP with our own, so that docker can pull images from our insecure registry, and change the images we want to use:

```
$ sed -i "s/192.168.1.11:5000/$MY_IP:5000/" global_vars.yml
$ sed -i "s/embercsi\/ember-csi:master/$MY_IP:5000\/ember-csi:testing/" global_vars.yml
```

With that, we are now ready to use our own custom image when deploying Ember-CSI in this example, but since we wanted to use the 3PAR backend we will also have to change the configuration editing `global_vars.yml` and changing the value of either `ember_lvm_config` or `ember_rbd_config` to replace one of the two backends.

### Deploy sysfiles secret (for adding backend specific file requirements)

#### Create 'system-files.tar' file

##### Example for Ceph backend

- Prepare the following tree structure:
    - etc/ceph/ceph.conf
    - etc/ceph/ceph.client.admin.keyring

- Create the archive:
    ```
    $ tar -cvf roles/master/files/system-files.tar etc
    ```

#### Modify 'global_vars.yml'

##### Modify values of ember_rbd_config

######  Example for an external Ceph backend
```
  ember_rbd_config: '{"name":"rbd","driver":"RBD","rbd_user":"admin","rbd_pool":"volumes","rbd_ceph_conf":"/etc/ceph/ceph.conf","rbd_keyring_conf":"/etc/ceph/ceph.client.admin.keyring"}'
```

## Usage

After the setup is completed the Kubernetes configuration is copied from the master node to the host. If we have the Kubernetes client installed (in Fedora you can install it with `sudo dnf install -y kubernetes-client`) we can use it from our own machine as follows:

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
ember-csi.io       8m
rbd.ember-csi.io   4m
```

Check the logs of the CSI *controller* to see that its running as expected:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -c csi-driver
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Running as controller with backend LVMVolumeDriver v3.0.0
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:17:03 default INFO ember_csi.common [req-15807873-3e8a-4107-b41a-6bd63ebdccb8] => GRPC GetPluginInfo
2019-02-14 14:17:03 default INFO ember_csi.common [req-15807873-3e8a-4107-b41a-6bd63ebdccb8] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:03 default INFO ember_csi.common [req-b0ab521b-fd7a-41f6-a03e-3328ebe3a6da] => GRPC Probe
2019-02-14 14:17:03 default INFO ember_csi.common [req-b0ab521b-fd7a-41f6-a03e-3328ebe3a6da] <= GRPC Probe served in 0s
2019-02-14 14:17:03 default INFO ember_csi.common [req-500d03fb-40d6-4eca-8188-07d2b2d6905c] => GRPC ControllerGetCapabilities
2019-02-14 14:17:03 default INFO ember_csi.common [req-500d03fb-40d6-4eca-8188-07d2b2d6905c] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:17:04 default INFO ember_csi.common [req-965509cc-2053-4257-afa9-d8d4ea3eeaf1] => GRPC GetPluginInfo
2019-02-14 14:17:04 default INFO ember_csi.common [req-965509cc-2053-4257-afa9-d8d4ea3eeaf1] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:04 default INFO ember_csi.common [req-214deb9d-aa3d-44d4-8cb4-7ebadaabfffc] => GRPC Probe
2019-02-14 14:17:04 default INFO ember_csi.common [req-214deb9d-aa3d-44d4-8cb4-7ebadaabfffc] <= GRPC Probe served in 0s
2019-02-14 14:17:04 default INFO ember_csi.common [req-ef6256e9-4445-481a-b3e9-cdfa0e09a41a] => GRPC GetPluginInfo
2019-02-14 14:17:04 default INFO ember_csi.common [req-ef6256e9-4445-481a-b3e9-cdfa0e09a41a] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:17:04 default INFO ember_csi.common [req-3ecc4201-423f-4d98-b0c3-4dfedcc111ea] => GRPC GetPluginCapabilities
2019-02-14 14:17:04 default INFO ember_csi.common [req-3ecc4201-423f-4d98-b0c3-4dfedcc111ea] <= GRPC GetPluginCapabilities served in 0s
2019-02-14 14:17:04 default INFO ember_csi.common [req-de7aec08-b728-432d-be69-27a6ed59d668] => GRPC ControllerGetCapabilities
2019-02-14 14:17:04 default INFO ember_csi.common [req-de7aec08-b728-432d-be69-27a6ed59d668] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:19:49 default INFO ember_csi.common [req-cc8dbfe3-7d92-48b6-9fea-b19f4e635fae] => GRPC Probe
2019-02-14 14:19:49 default INFO ember_csi.common [req-cc8dbfe3-7d92-48b6-9fea-b19f4e635fae] <= GRPC Probe served in 0s
2019-02-14 14:21:19 default INFO ember_csi.common [req-6838a1e3-a7d5-4689-a71f-399a21930788] => GRPC Probe
2019-02-14 14:21:19 default INFO ember_csi.common [req-6838a1e3-a7d5-4689-a71f-399a21930788] <= GRPC Probe served in 0s
2019-02-14 14:22:49 default INFO ember_csi.common [req-212bb19e-3e0a-46ce-9a66-32eaca2c15e4] => GRPC Probe
2019-02-14 14:22:49 default INFO ember_csi.common [req-212bb19e-3e0a-46ce-9a66-32eaca2c15e4] <= GRPC Probe served in 0s
2019-02-14 14:24:19 default INFO ember_csi.common [req-cbb20af4-5eb6-4e1a-a8ea-0132022f8c48] => GRPC Probe
2019-02-14 14:24:19 default INFO ember_csi.common [req-cbb20af4-5eb6-4e1a-a8ea-0132022f8c48] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-rbd-0 -c csi-driver
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Running as controller with backend RBDDriver v1.2.0
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:21:15 rbd INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-f261da91-6b20-48a8-9a5c-26cd16b6ab13] => GRPC GetPluginInfo
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-f261da91-6b20-48a8-9a5c-26cd16b6ab13] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-503b6596-f408-4b91-94be-63557ef1ffa8] => GRPC GetPluginInfo
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-503b6596-f408-4b91-94be-63557ef1ffa8] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-4664c4d5-407e-4e78-91d2-ad2fef3c8176] => GRPC Probe
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-4664c4d5-407e-4e78-91d2-ad2fef3c8176] <= GRPC Probe served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-4fd5961f-884d-4029-936b-08e98bee41d9] => GRPC ControllerGetCapabilities
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-4fd5961f-884d-4029-936b-08e98bee41d9] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-fb6fbddf-e930-45f3-a476-d1a3212c7cfa] => GRPC Probe
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-fb6fbddf-e930-45f3-a476-d1a3212c7cfa] <= GRPC Probe served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-3f079fea-f519-401e-b3ff-c0355abf4176] => GRPC GetPluginInfo
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-3f079fea-f519-401e-b3ff-c0355abf4176] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-7b0c6db7-e426-460a-beb6-0499becfe3ff] => GRPC GetPluginCapabilities
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-7b0c6db7-e426-460a-beb6-0499becfe3ff] <= GRPC GetPluginCapabilities served in 0s
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-84b46ba5-3b06-4f8d-8295-689795b7a9b9] => GRPC ControllerGetCapabilities
2019-02-14 14:21:16 rbd INFO ember_csi.common [req-84b46ba5-3b06-4f8d-8295-689795b7a9b9] <= GRPC ControllerGetCapabilities served in 0s
2019-02-14 14:24:11 rbd INFO ember_csi.common [req-74bf9abc-80b6-40ca-a032-ff761a389a2d] => GRPC Probe
2019-02-14 14:24:11 rbd INFO ember_csi.common [req-74bf9abc-80b6-40ca-a032-ff761a389a2d] <= GRPC Probe served in 0s
2019-02-14 14:25:41 rbd INFO ember_csi.common [req-a85e05d9-3c71-42f6-8c67-48ac7151667b] => GRPC Probe
2019-02-14 14:25:41 rbd INFO ember_csi.common [req-a85e05d9-3c71-42f6-8c67-48ac7151667b] <= GRPC Probe served in 0s
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
    Name:     ember-csi.io
    Node ID:  ember-csi.io.node0
    Topology Keys:
      iscsi
    Name:     rbd.ember-csi.io
    Node ID:  rbd.ember-csi.node0
    Topology Keys:
      rbd
Status:
  Drivers:
    Available:                true
    Name:                     ember-csi.io
    Volume Plugin Mechanism:  in-tree
    Available:                true
    Name:                     rbd.ember-csi.io
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
    Name:     ember-csi.io
    Node ID:  node1.ember-csi.io
    Topology Keys:
      iscsi
    Name:     rbd.ember-csi.io
    Node ID:  rbd.ember-csi.io.node1
    Topology Keys:
      rbd
Status:
  Drivers:
    Available:                true
    Name:                     ember-csi.io
    Volume Plugin Mechanism:  in-tree
    Available:                true
    Name:                     rbd.ember-csi.io
    Volume Plugin Mechanism:  in-tree
Events:                       <none>
```

Check the CSI *node* logs:

```
[vagrant@master ~]$ kubectl logs csi-node-0-jpdsg -c csi-driver
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:18:47 default INFO ember_csi.common [req-56458a2d-4e73-402a-b16c-c3f69768b11b] => GRPC GetPluginInfo
2019-02-14 14:18:47 default INFO ember_csi.common [req-56458a2d-4e73-402a-b16c-c3f69768b11b] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:18:47 default INFO ember_csi.common [req-250d90d5-3d38-4397-b66a-596bc1f5b811] => GRPC NodeGetInfo
2019-02-14 14:18:47 default INFO ember_csi.common [req-250d90d5-3d38-4397-b66a-596bc1f5b811] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:21:07 default INFO ember_csi.common [req-86778156-094d-42a5-a4e5-510036adbed2] => GRPC Probe
2019-02-14 14:21:07 default INFO ember_csi.common [req-86778156-094d-42a5-a4e5-510036adbed2] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-qf4ld -c csi-driver
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:18:46 default INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:18:48 default INFO ember_csi.common [req-14bc25a5-2585-4748-8051-3b3f9bd3bba3] => GRPC GetPluginInfo
2019-02-14 14:18:48 default INFO ember_csi.common [req-14bc25a5-2585-4748-8051-3b3f9bd3bba3] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:18:48 default INFO ember_csi.common [req-f76992d8-f919-41b5-80d7-7a4bc597e288] => GRPC NodeGetInfo
2019-02-14 14:18:48 default INFO ember_csi.common [req-f76992d8-f919-41b5-80d7-7a4bc597e288] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:22:05 default INFO ember_csi.common [req-8092dad2-9c44-4fff-bfd0-c90c1823d014] => GRPC Probe
2019-02-14 14:22:05 default INFO ember_csi.common [req-8092dad2-9c44-4fff-bfd0-c90c1823d014] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-rbd-k5dx5 -c csi-driver
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (cinder: v1.0.0.dev16644, CSI spec: v1.0.0)
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:20:45 rbd INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:20:45 rbd INFO ember_csi.common [req-a12f4699-c94d-4626-8406-f002f895b425] => GRPC GetPluginInfo
2019-02-14 14:20:45 rbd INFO ember_csi.common [req-a12f4699-c94d-4626-8406-f002f895b425] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:20:45 rbd INFO ember_csi.common [req-d7200eb2-4a96-448a-8917-aa06f629e5c2] => GRPC NodeGetInfo
2019-02-14 14:20:45 rbd INFO ember_csi.common [req-d7200eb2-4a96-448a-8917-aa06f629e5c2] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:23:25 rbd INFO ember_csi.common [req-942c9ddc-fa92-42e0-834d-b8af7064a68d] => GRPC Probe
2019-02-14 14:23:25 rbd INFO ember_csi.common [req-942c9ddc-fa92-42e0-834d-b8af7064a68d] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-node-rbd-mrxwc -c csi-driver
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Running as node
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2019-02-14 14:20:46 rbd INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2019-02-14 14:20:47 rbd INFO ember_csi.common [req-39458128-8012-4d54-b109-ce1acaa9f119] => GRPC GetPluginInfo
2019-02-14 14:20:47 rbd INFO ember_csi.common [req-39458128-8012-4d54-b109-ce1acaa9f119] <= GRPC GetPluginInfo served in 0s
2019-02-14 14:20:47 rbd INFO ember_csi.common [req-356c4a6e-3d9d-4bba-a42e-039f1b00d183] => GRPC NodeGetInfo
2019-02-14 14:20:47 rbd INFO ember_csi.common [req-356c4a6e-3d9d-4bba-a42e-039f1b00d183] <= GRPC NodeGetInfo served in 0s
2019-02-14 14:22:48 rbd INFO ember_csi.common [req-41843054-b08e-4e4b-b581-6cf3f855293b] => GRPC Probe
2019-02-14 14:22:48 rbd INFO ember_csi.common [req-41843054-b08e-4e4b-b581-6cf3f855293b] <= GRPC Probe served in 0s
```


Check the connection information that the Ember-CSI *node* services are storing in Kubernetes CRD objects to be used by the *controller* to export and map volumes to them:

```
[vagrant@master ~]$ kubectl get keyvalue
NAME                                       AGE
ember-csi.io.controller.master.probe       21m
ember-csi.io.node.node0.probe              17m
ember-csi.io.node.node1.probe              17m
ember-csi.io.node0                         20m
ember-csi.io.node1                         20m
rbd.ember-csi.io.controller.master.probe   17m
rbd.ember-csi.io.node.node0.probe          15m
rbd.ember-csi.io.node.node1.probe          15m
rbd.ember-csi.io.node0                     18m
rbd.ember-csi.io.node1                     18m


[vagrant@master ~]$ kubectl describe keyvalue
Name:         ember-csi.io.node0
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
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/ember-csi.io.node0
  UID:                 70332e8d-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         ember-csi.io.node1
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
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/ember-csi.io.node1
  UID:                 7033259c-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         ember-csi.io.rbd.node0
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
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/rbd.ember-csi.io.node0
  UID:                 b7ef3ad5-3063-11e9-aed5-5254002dbb88
Events:                <none>


Name:         rbd.ember-csi.io.node1
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
  Self Link:           /apis/ember-csi.io/v1/namespaces/default/keyvalues/rbd.ember-csi.io.node1
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
Annotations:       pv.kubernetes.io/provisioned-by: ember-csi.io
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
    Driver:            ember-csi.io
    VolumeHandle:      540c5a37-ce98-4b47-83f7-10c54a4777b9
    ReadOnly:          false
    VolumeAttributes:      storage.kubernetes.io/csiProvisionerIdentity=1550153767135-8081-ember-csi.io
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
2019-02-14 14:17:03 default INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)


[ . . .]

2019-02-14 14:52:49 default INFO ember_csi.common [req-d135903b-f89a-4030-a085-5aa0ba3be2be] => GRPC Probe
2019-02-14 14:52:49 default INFO ember_csi.common [req-d135903b-f89a-4030-a085-5aa0ba3be2be] <= GRPC Probe served in 0s
2019-02-14 14:53:29 default INFO ember_csi.common [req-b5388936-239c-4285-896b-29a9e764caa7] => GRPC ControllerPublishVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:31 default INFO ember_csi.common [req-b5388936-239c-4285-896b-29a9e764caa7] <= GRPC ControllerPublishVolume served in 2s
^C
```

Tail the CSI *node* plugin logs to see that the plugin actually attaches the volume to the container:

```
[vagrant@master ~]$ kubectl logs csi-node-qf4ld -fc csi-driver
2019-02-14 14:18:46 INFO ember_csi.ember_csi [-] Ember CSI v0.0.2 with 30 workers (CSI spec: v1.0.0, cinderlib: v0.3.10.dev4, cinder: v13.1.0.dev902)

[ . . . ]

2019-02-14 14:53:44 default INFO ember_csi.common [req-c9ed9f88-920a-432c-9bb3-d8562d21fadf] => GRPC Probe
2019-02-14 14:53:44 default INFO ember_csi.common [req-c9ed9f88-920a-432c-9bb3-d8562d21fadf] <= GRPC Probe served in 0s
2019-02-14 14:53:45 default INFO ember_csi.common [req-030e7f15-8f75-49d4-8cc6-3e7ec84698a3] => GRPC NodeGetCapabilities
2019-02-14 14:53:45 default INFO ember_csi.common [req-030e7f15-8f75-49d4-8cc6-3e7ec84698a3] <= GRPC NodeGetCapabilities served in 0s
2019-02-14 14:53:45 default INFO ember_csi.common [req-62b267b9-fcf7-48d1-a450-97519952af1c] => GRPC NodeStageVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:47 default WARNING os_brick.initiator.connectors.iscsi [req-62b267b9-fcf7-48d1-a450-97519952af1c] iscsiadm stderr output when getting sessions: iscsiadm: No active sessions.

2019-02-14 14:53:50 default INFO ember_csi.common [req-62b267b9-fcf7-48d1-a450-97519952af1c] <= GRPC NodeStageVolume served in 5s
2019-02-14 14:53:50 default INFO ember_csi.common [req-8414718e-6f5a-4eed-84f0-29cbfca3657e] => GRPC NodeGetCapabilities
2019-02-14 14:53:50 default INFO ember_csi.common [req-8414718e-6f5a-4eed-84f0-29cbfca3657e] <= GRPC NodeGetCapabilities served in 0s
2019-02-14 14:53:50 default INFO ember_csi.common [req-ce8f5d78-b07b-45d0-9c4e-8c89defd5223] => GRPC NodePublishVolume 540c5a37-ce98-4b47-83f7-10c54a4777b9
2019-02-14 14:53:50 default INFO ember_csi.common [req-ce8f5d78-b07b-45d0-9c4e-8c89defd5223] <= GRPC NodePublishVolume served in 0s
2019-02-14 14:55:05 default INFO ember_csi.common [req-ba73aa46-6bb9-4b27-974a-aa2fa160b8ff] => GRPC Probe
2019-02-14 14:55:05 default INFO ember_csi.common [req-ba73aa46-6bb9-4b27-974a-aa2fa160b8ff] <= GRPC Probe served in 0s
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

Since Ember-CSI also supports raw block volumes we'll create one:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/10-pvc-block.yml
persistentvolumeclaim/csi-block-pvc created
```

Now we confirm that the PVC has the `VolumeMode` set to `Block`:

```
[vagrant@master ~]$ kubectl describe pvc csi-block-pvc
Name:          csi-block-pvc
Namespace:     default
StorageClass:  csi-sc
Status:        Bound
Volume:        pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe
Labels:        <none>
Annotations:   pv.kubernetes.io/bind-completed: yes
               pv.kubernetes.io/bound-by-controller: yes
               volume.beta.kubernetes.io/storage-provisioner: ember-csi.io
Finalizers:    [kubernetes.io/pvc-protection]
Capacity:      3Gi
Access Modes:  RWO
VolumeMode:    Block
Events:
  Type       Reason                 Age   From                                                      Message
  ----       ------                 ----  ----                                                      -------
  Normal     ExternalProvisioning   42s   persistentvolume-controller                               waiting for a volume to be created, either by external provisioner "ember-csi.io" or manually created by system administrator
  Normal     Provisioning           42s   ember-csi.io_master_3905aa08-3f42-11e9-82e2-525400ba8dbe  External provisioner is provisioning volume for claim "default/csi-block-pvc"
  Normal     ProvisioningSucceeded  41s   ember-csi.io_master_3905aa08-3f42-11e9-82e2-525400ba8dbe  Successfully provisioned volume pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe
Mounted By:  <none>
```

And with the name of the Volume we can see that the PV is also `Block`:

```
[vagrant@master ~]$ k describe pv pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe
Name:              pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe
Labels:            <none>
Annotations:       pv.kubernetes.io/provisioned-by: ember-csi.io
Finalizers:        [kubernetes.io/pv-protection]
StorageClass:      csi-sc
Status:            Bound
Claim:             default/csi-block-pvc
Reclaim Policy:    Delete
Access Modes:      RWO
VolumeMode:        Block
Capacity:          3Gi
Node Affinity:
  Required Terms:
    Term 0:        iscsi in [true]
Message:
Source:
    Type:              CSI (a Container Storage Interface (CSI) volume source)
    Driver:            ember-csi.io
    VolumeHandle:      684a33bf-da59-4b60-b986-7203281e5a3c
    ReadOnly:          false
    VolumeAttributes:      storage.kubernetes.io/csiProvisionerIdentity=1551788866849-8081-ember-csi.io
Events:                <none>
```

It's time to use this raw block volume on a container:

```
[vagrant@master ~]$ kubectl create -f kubeyml/lvm/11-app-block.yml
pod/my-csi-block-app created
```

And now see that the raw volume is there:

```
[vagrant@master ~]$ kubectl get pod my-csi-block-app
NAME               READY   STATUS    RESTARTS   AGE
my-csi-block-app   1/1     Running   0          74s

[vagrant@master ~]$ kubectl -it exec my-csi-block-app -- ls -la /dev/ember0
brw-rw----    1 root     disk        8,  32 Mar  5 12:47 /dev/ember0
```

We can now repeat all these same steps with the RBD backend that, according to the topology we've defined, can be accessed from all of our worker nodes:

```
[vagrant@master ~]$ kubectl create -f kubeyml/rbd/05-pvc.yml
persistentvolumeclaim/csi-rbd created


[vagrant@master ~]$ kubectl get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                   STORAGECLASS   REASON   AGE
pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe   3Gi        RWO            Delete           Bound    default/csi-block-pvc   csi-sc                  1m
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

[vagrant@master ~]$ kubectl create -f kubeyml/rbd/10-pvc-block.yml
persistentvolumeclaim/csi-rbd-block created

[vagrant@master ~]$ kubectl get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                       STORAGECLASS   REASON   AGE
pvc-1117b711-306a-11e9-aed5-5254002dbb88   2Gi        RWO            Delete           Bound    default/vol-from-snap-rbd   csi-rbd                 11s
pvc-1bc1442e-3f44-11e9-93df-525400ba8dbe   3Gi        RWO            Delete           Bound    default/csi-block-pvc       csi-sc                  2m32s
pvc-7537f440-3069-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/vol-from-snap       csi-sc                  4m31s
pvc-7db8685b-3066-11e9-aed5-5254002dbb88   1Gi        RWO            Delete           Bound    default/csi-pvc             csi-sc                  25m
pvc-ac9a3111-3f46-11e9-93df-525400ba8dbe   3Gi        RWO            Delete           Bound    default/csi-rbd-block       csi-rbd                 19s
pvc-ddf984b7-3069-11e9-aed5-5254002dbb88   2Gi        RWO            Delete           Bound    default/csi-rbd             csi-rbd                 95s

[vagrant@master ~]$ kubectl create -f kubeyml/rbd/09-app-from-snap-vol.yml
pod/my-csi-app-rbd-2 created

[vagrant@master ~]$ kubectl create -f kubeyml/rbd/11-app-block.yml
pod/my-csi-block-app-rbd created

[vagrant@master ~]$ kubectl get pod
NAME                   READY   STATUS    RESTARTS   AGE
csi-controller-0       6/6     Running   0          52m
csi-node-0-jpdsg       3/3     Running   1          50m
csi-node-qf4ld         3/3     Running   1          50m
csi-node-rbd-k5dx5     3/3     Running   0          47m
csi-node-rbd-mrxwc     3/3     Running   0          47m
csi-rbd-0              7/7     Running   1          47m
my-csi-app             1/1     Running   0          14m
my-csi-app-2           1/1     Running   0          4m54s
my-csi-app-rbd         1/1     Running   0          3m1s
my-csi-app-rbd-2       1/1     Running   0          84s
my-csi-block-app       1/1     Running   0          4m
my-csi-block-app-rbd   1/1     Running   0          77s

[vagrant@master ~]$ kubectl describe pod my-csi-app-rbd |grep Node:
Node:               node0/192.168.10.100


[vagrant@master ~]$ kubectl describe pod my-csi-app-rbd-2 |grep Node:
Node:               node1/192.168.10.101


[vagrant@master ~]$ kubectl describe pod my-csi-block-app-rbd |grep Node:
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
connection.ember-csi.io/489259c2-116e-4888-b48f-cd7e1e27b2e4   8m
connection.ember-csi.io/63394bf4-9153-4c9c-9e76-aa73d5b80b48   16m
connection.ember-csi.io/a96e8e33-f14e-46e6-8732-67efae593539   5m
connection.ember-csi.io/cf2800e7-018f-44d7-8880-c971a74d87ef   3m
connection.ember-csi.io/eeb85633-a554-4b2d-aabe-a8bf5c3b7f41   3m

NAME                                                       AGE
volume.ember-csi.io/20c798a2-ba98-4479-9167-6ee253b7601e   12m
volume.ember-csi.io/540c5a37-ce98-4b47-83f7-10c54a4777b9   29m
volume.ember-csi.io/684a33bf-da59-4b60-b986-7203281e5a3c   4m
volume.ember-csi.io/9e1e7f95-2007-4775-92a8-896881b22618   3m
volume.ember-csi.io/f91e729e-e9d1-4a28-89f8-293423047eea   5m
volume.ember-csi.io/faa72ced-43ef-45ac-9bfe-5781e15f75da   8m

NAME                                                             AGE
keyvalue.ember-csi.io/ember-csi.io.controller.master.probe       52m
keyvalue.ember-csi.io/ember-csi.io.node.node0.probe              48m
keyvalue.ember-csi.io/ember-csi.io.node.node1.probe              48m
keyvalue.ember-csi.io/ember-csi.io.node0                         51m
keyvalue.ember-csi.io/ember-csi.io.node1                         51m
keyvalue.ember-csi.io/rbd.ember-csi.io.controller.master.probe   48m
keyvalue.ember-csi.io/rbd.ember-csi.io.node.node0.probe          46m
keyvalue.ember-csi.io/rbd.ember-csi.io.node.node1.probe          46m
keyvalue.ember-csi.io/rbd.ember-csi.io.node0                     49m
keyvalue.ember-csi.io/rbd.ember-csi.io.node1                     49m
```


Remember that, for debugging purposes, besides the logs, you can also get a Python console on GRPC requests by starting the debug mode, then executing bash into the node, installing `nmap-ncat`, and when a request is made connecting to port 4444.  For example, to toggle debug mode on the controller node:


```
$ kubectl exec csi-controller-0 -c csi-driver -- kill -USR1 1
```
