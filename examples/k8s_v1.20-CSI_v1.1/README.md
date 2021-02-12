# Kubernetes example

This is a demo for Ember-CSI as a CSI v1.1 plugin, deployed in Kubernetes 1.20, running on CentOS 8, to showcase all its functionality: volume creation, cloning, and deletion, creating snapshots and volumes from them, extending volumes, topology, liveness probes, etc.

It deploys a scenario where we have segregated an infra node from the 2 workload nodes, and the 2 CSI plugins are deployed on the infra node.

The 2 Ember-CSI plugins deployed are LVM iSCSI and Ceph RBD, and to illustrate the topology feature the LVM iSCSI backend is only accessible by workload *node0*, whereas the Ceph RBD backend is accessible from all workload nodes and is set as the default storage class.

This example uses Vagrant, libvirt, KVM, and Ansible to create and provision these 3 VMs.

**These Ansible playbooks are not idempotent, so don't run them more than once**

This demo is based on Luis Pabon's [Kubeup repository](https://github.com/lpabon/kubeup).

## Requirements

* Install vagrant, ansible, and a hypervisor

    - Fedora

    ```
    $ sudo dnf -y install vagrant ansible
    ```

* Hypervisor:

  1. QEMU-KVM is the default hypervisor -KVM and you'll need to install qemu-kvm, libvirt, and vagrant-libvirt packages, as well as start the libvirt service:

     - Fedora

     ```
     $ sudo dnf -y install qemu-kvm libvirt vagrant-libvirt

     $ sudo systemctl start libvirtd
     ```

  2. Virtualbox is also supported


## Configuration

Running the demo with the default LVM and RBD storage backends requires no configuration changes.

If we want to use a different storage backend we need to edit the `kubeyml/lvm/01-controller.yml` or `kubeyml/rbd/01-controller.yml` file to change the storage configuration for the CSI plugin. This is done by changing the *value* of the `X_CSI_BACKEND_CONFIG` environmental variable with our own driver configuration.  For more information on the specific driver configuration please refer to the [cinderlib documentation](https://docs.openstack.org/cinderlib), specifically to the [Backend section](https://docs.openstack.org/cinderlib/latest/topics/backends.html), and the [Validated drivers' section](https://docs.openstack.org/cinderlib/latest/validated.html).

The `Vagranfile` defines 2 nodes and a master, each with 4GB and 2 cores.  This can be changed using variables `NODES`, `MEMORY`, and `CPUS` in this file.


## Setup

The demo supports local and remote libvirt, for those that use an external box where they run their VMs.

Local setup of the demo can be done running the `up.sh` script, and for the default hypervisor you'll only need to call it, but for other hypervisors you'll have to pass the hypervisor on the call.  Be aware that this command takes a while to run:

For VirtualBox:

```
$ ./up.sh virtualbox
Bringing machine 'master' up with 'virtualbox' provider...
Bringing machine 'node0' up with 'virtualbox' provider...
Bringing machine 'node1' up with 'virtualbox' provider...
==> master: Checking if box 'centos/8' is up to date...
==> node1: Checking if box 'centos/8' is up to date...
==> node0: Checking if box 'centos/8' is up to date...

[ . . . ]

PLAY RECAP *********************************************************************
master                     : ok=69   changed=57   unreachable=0    failed=0
node0                      : ok=22   changed=20   unreachable=0    failed=0
node1                      : ok=22   changed=20   unreachable=0    failed=0
```

For QEMU-KVM:

```
$ ./up.sh
Bringing machine 'master' up with 'libvirt' provider...
Bringing machine 'node0' up with 'libvirt' provider...
Bringing machine 'node1' up with 'libvirt' provider...
==> master: Checking if box 'centos/8' is up to date...
==> node1: Checking if box 'centos/8' is up to date...
==> node0: Checking if box 'centos/8' is up to date...

[ . . . ]

PLAY RECAP *********************************************************************
master                     : ok=69   changed=57   unreachable=0    failed=0
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
==> master: Checking if box 'centos/8' is up to date...
==> node1: Checking if box 'centos/8' is up to date...
==> node0: Checking if box 'centos/8' is up to date...

[ . . . ]

PLAY RECAP *********************************************************************
master                     : ok=69   changed=57   unreachable=0    failed=0
node0                      : ok=22   changed=20   unreachable=0    failed=0
node1                      : ok=22   changed=20   unreachable=0    failed=0
```


## Usage

After the setup is completed the Kubernetes configuration is copied from the master node to the host. If we have the Kubernetes client installed (in Fedora you can install it with `sudo dnf install -y kubernetes-client`) we can use it from our own machine as follows:

```
$ kubectl --kubeconfig=kubeconfig.conf get nodes
NAME     STATUS   ROLES    AGE   VERSION
master   Ready    master   10m   v1.16.2
node0    Ready    <none>   10m   v1.16.2
node1    Ready    <none>   10m   v1.16.2
```

Or we can just SSH into the master and run commands in there:
```
$ vagrant ssh master
Last login: Tue Jul 24 10:12:40 2018 from 192.168.121.1
[vagrant@master ~]$ kubectl get nodes
NAME     STATUS   ROLES    AGE   VERSION
master   Ready    master   10m   v1.16.2
node0    Ready    <none>   10m   v1.16.2
node1    Ready    <none>   10m   v1.16.2
```

Unless stated otherwise, all the following commands are run assuming we are in the *master* node.

We can check that the CSI *controller* services are running in master and that they have been registered in Kubernetes as `CSIDrivers.csi.storage.k8s.io` objects:

```
[vagrant@master ~]$ kubectl get pod csi-controller-0 csi-rbd-0
NAME               READY   STATUS    RESTARTS   AGE
csi-controller-0   7/7     Running   0          8m50s
csi-rbd-0          8/8     Running   1          4m12s


[vagrant@master ~]$ kubectl describe pod csi-controller-0 csi-rbd-0 |grep Node:
Node:               master/192.168.10.90
Node:               master/192.168.10.90


[vagrant@master ~]$ kubectl get csidrivers
NAME               CREATED AT
ember-csi.io       2020-04-07T14:49:18Z
rbd.ember-csi.io   2020-04-07T14:49:40Z
```

Check the logs of the CSI *controller* to see that its running as expected:

```
[vagrant@master ~]$ kubectl logs csi-controller-0 -c csi-driver


2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Ember CSI v0.9.0-12-662c358+07042020143656555198011 with 30 workers (CSI spec: v1.1.0, cinderlib: v1.1.0.dev12, cinder: v15.1.0.dev142)
2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Running as controller with backend LVMVolumeDriver v3.0.0
2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2020-04-07 14:17:03 default INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2020-04-07 14:17:03 default INFO ember_csi.common [req-15807873-3e8a-4107-b41a-6bd63ebdccb8] => GRPC GetPluginInfo
2020-04-07 14:17:03 default INFO ember_csi.common [req-15807873-3e8a-4107-b41a-6bd63ebdccb8] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:17:03 default INFO ember_csi.common [req-b0ab521b-fd7a-41f6-a03e-3328ebe3a6da] => GRPC Probe
2020-04-07 14:17:03 default INFO ember_csi.common [req-b0ab521b-fd7a-41f6-a03e-3328ebe3a6da] <= GRPC Probe served in 0s
2020-04-07 14:17:03 default INFO ember_csi.common [req-500d03fb-40d6-4eca-8188-07d2b2d6905c] => GRPC ControllerGetCapabilities
2020-04-07 14:17:03 default INFO ember_csi.common [req-500d03fb-40d6-4eca-8188-07d2b2d6905c] <= GRPC ControllerGetCapabilities served in 0s
2020-04-07 14:17:04 default INFO ember_csi.common [req-965509cc-2053-4257-afa9-d8d4ea3eeaf1] => GRPC GetPluginInfo
2020-04-07 14:17:04 default INFO ember_csi.common [req-965509cc-2053-4257-afa9-d8d4ea3eeaf1] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:17:04 default INFO ember_csi.common [req-214deb9d-aa3d-44d4-8cb4-7ebadaabfffc] => GRPC Probe
2020-04-07 14:17:04 default INFO ember_csi.common [req-214deb9d-aa3d-44d4-8cb4-7ebadaabfffc] <= GRPC Probe served in 0s
2020-04-07 14:17:04 default INFO ember_csi.common [req-ef6256e9-4445-481a-b3e9-cdfa0e09a41a] => GRPC GetPluginInfo
2020-04-07 14:17:04 default INFO ember_csi.common [req-ef6256e9-4445-481a-b3e9-cdfa0e09a41a] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:17:04 default INFO ember_csi.common [req-3ecc4201-423f-4d98-b0c3-4dfedcc111ea] => GRPC GetPluginCapabilities
2020-04-07 14:17:04 default INFO ember_csi.common [req-3ecc4201-423f-4d98-b0c3-4dfedcc111ea] <= GRPC GetPluginCapabilities served in 0s
2020-04-07 14:17:04 default INFO ember_csi.common [req-de7aec08-b728-432d-be69-27a6ed59d668] => GRPC ControllerGetCapabilities
2020-04-07 14:17:04 default INFO ember_csi.common [req-de7aec08-b728-432d-be69-27a6ed59d668] <= GRPC ControllerGetCapabilities served in 0s
2020-04-07 14:19:49 default INFO ember_csi.common [req-cc8dbfe3-7d92-48b6-9fea-b19f4e635fae] => GRPC Probe
2020-04-07 14:19:49 default INFO ember_csi.common [req-cc8dbfe3-7d92-48b6-9fea-b19f4e635fae] <= GRPC Probe served in 0s
2020-04-07 14:21:19 default INFO ember_csi.common [req-6838a1e3-a7d5-4689-a71f-399a21930788] => GRPC Probe
2020-04-07 14:21:19 default INFO ember_csi.common [req-6838a1e3-a7d5-4689-a71f-399a21930788] <= GRPC Probe served in 0s
2020-04-07 14:22:49 default INFO ember_csi.common [req-212bb19e-3e0a-46ce-9a66-32eaca2c15e4] => GRPC Probe
2020-04-07 14:22:49 default INFO ember_csi.common [req-212bb19e-3e0a-46ce-9a66-32eaca2c15e4] <= GRPC Probe served in 0s
2020-04-07 14:24:19 default INFO ember_csi.common [req-cbb20af4-5eb6-4e1a-a8ea-0132022f8c48] => GRPC Probe
2020-04-07 14:24:19 default INFO ember_csi.common [req-cbb20af4-5eb6-4e1a-a8ea-0132022f8c48] <= GRPC Probe served in 0s


[vagrant@master ~]$ kubectl logs csi-rbd-0 -c csi-driver
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Ember CSI v0.9.0-12-662c358+07042020143656555198011 with 30 workers (CSI spec: v1.1.0, cinderlib: v1.1.0.dev12, cinder: v15.1.0.dev142)
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Persistence module: CRDPersistence
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Running as controller with backend RBDDriver v1.2.0
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Debugging feature is ENABLED with ember_csi.rpdb and OFF. Toggle it with SIGUSR1.
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Supported filesystems: cramfs, minix, btrfs, ext2, ext3, ext4, xfs
2020-04-07 14:21:15 rbd INFO ember_csi.ember_csi [-] Now serving on unix:///csi-data/csi.sock...
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-f261da91-6b20-48a8-9a5c-26cd16b6ab13] => GRPC GetPluginInfo
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-f261da91-6b20-48a8-9a5c-26cd16b6ab13] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-503b6596-f408-4b91-94be-63557ef1ffa8] => GRPC GetPluginInfo
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-503b6596-f408-4b91-94be-63557ef1ffa8] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-4664c4d5-407e-4e78-91d2-ad2fef3c8176] => GRPC Probe
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-4664c4d5-407e-4e78-91d2-ad2fef3c8176] <= GRPC Probe served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-4fd5961f-884d-4029-936b-08e98bee41d9] => GRPC ControllerGetCapabilities
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-4fd5961f-884d-4029-936b-08e98bee41d9] <= GRPC ControllerGetCapabilities served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-fb6fbddf-e930-45f3-a476-d1a3212c7cfa] => GRPC Probe
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-fb6fbddf-e930-45f3-a476-d1a3212c7cfa] <= GRPC Probe served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-3f079fea-f519-401e-b3ff-c0355abf4176] => GRPC GetPluginInfo
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-3f079fea-f519-401e-b3ff-c0355abf4176] <= GRPC GetPluginInfo served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-7b0c6db7-e426-460a-beb6-0499becfe3ff] => GRPC GetPluginCapabilities
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-7b0c6db7-e426-460a-beb6-0499becfe3ff] <= GRPC GetPluginCapabilities served in 0s
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-84b46ba5-3b06-4f8d-8295-689795b7a9b9] => GRPC ControllerGetCapabilities
2020-04-07 14:21:16 rbd INFO ember_csi.common [req-84b46ba5-3b06-4f8d-8295-689795b7a9b9] <= GRPC ControllerGetCapabilities served in 0s
2020-04-07 14:24:11 rbd INFO ember_csi.common [req-74bf9abc-80b6-40ca-a032-ff761a389a2d] => GRPC Probe
2020-04-07 14:24:11 rbd INFO ember_csi.common [req-74bf9abc-80b6-40ca-a032-ff761a389a2d] <= GRPC Probe served in 0s
2020-04-07 14:25:41 rbd INFO ember_csi.common [req-a85e05d9-3c71-42f6-8c67-48ac7151667b] => GRPC Probe
2020-04-07 14:25:41 rbd INFO ember_csi.common [req-a85e05d9-3c71-42f6-8c67-48ac7151667b] <= GRPC Probe served in 0s
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

From here we can use the different YAML files that exist under `kubeyml/rbd` and `kubeyml/lvm` to explore the functionality of the plugin:

1. Create a mount volume: `05-pvc.yml`
2. Use said volume in a container: `06-app.yml`
3. Create a snapshot of the volume from step #1: `07-snapshot.yml`
4. Create a volume from the snapshot from step #3: `08-restore-snapshot.yml`
5. Use the volume from step #4 on a container: `09-app-from-snap-vol.yml`
6. Use the snapshot from step #3 to create a volume larger than the source snapshot: `10-restore-snapshot-larger-volume.yml`
7. Use the volume from step #6 in a container: `11-app-from-snap-larger-vol.yml`
8. Create a raw block volume: `12-pvc-block.yml`
9. Use the block volume from step #8 in a container: `13-app-block.yml`
10. Clone the block volume: `14-clone-block.yml`
11. Use cloned block volume in a container: `15-app-cloned-block.yml`
12. Clone the volume from step #8 into a larger volume: `16-clone-block-larger.yml`
13. Use volume from step #12 in a container: `17-app-cloned-larger-block.yml`
14. Resize, attached or available, volume from step #10 (Use `kubectl apply` and not `create`): `18-resize-pvc-block.yml`
15. Resize volume from step #1 (Use `kubectl apply` and not `create`): `19-resize-pvc.yml`
16. Create a multi-writer (RWX) block volume: `20-rwx-pvc-block.yml`
17. Use the RWX volume in 2 different pods : `21-app-rwx-block.yml`
18. Create a multi-reader (ROX) block volume: `22-rox-pvc-block.yml`
19. Use the ROX volume in 2 different pods: `23-app-rox-block.yml`

In steps 17 and 19 the pods will be created on the same node for the LVM backend (because of the artifical topology constraints we have set) and on different nodes for the RBD backend.

Create a 1GB volume on the LVM backend using provided PVC manifest:

Each one of the CSI pods is running the `embercsi/csc` container, allowing us to easily send CSI commands directly to the Ember-CSI service running in a pod using the [Container Storage Client](https://github.com/rexray/gocsi/tree/master/csc).

For example, we can request the LVM CSI *controller* plugin to list volumes with:

```
[vagrant@master ~]$ kubectl exec -c csc csi-controller-0 csc controller list-volumes
"4363660e-6322-4e96-941c-19ce3e6aae43"  1073741824
```

All the internal Ember-CSI metadata is grouped under the name `ember`, and we can get it all like this:

```
[vagrant@master ~]$ kubectl get ember
NAME                                                       AGE
volume.ember-csi.io/0f750aba-33ec-4529-a2fa-39267af37755   7m29s
volume.ember-csi.io/4363660e-6322-4e96-941c-19ce3e6aae43   22m
volume.ember-csi.io/5af01a7e-3201-4de0-961e-f5cb9de30bd9   14m
volume.ember-csi.io/6898560d-fabc-4220-9652-adcf74e53133   11m
volume.ember-csi.io/9a43c786-c973-4cda-a6a8-da78313e2837   3m31s
volume.ember-csi.io/d13d38d4-f90d-4837-8a37-64378210a48d   17m

NAME                                                         AGE
snapshot.ember-csi.io/0a4debad-7f2d-4a9c-8932-ea6288b03af6   17m

NAME                                                           AGE
connection.ember-csi.io/4d843cfc-fa5c-4927-ae24-e520b6e1af85   13m
connection.ember-csi.io/61afb225-e59f-4b2e-9720-2147a28b505a   3m8s
connection.ember-csi.io/8b28e507-3532-42db-8299-ecc38ba134af   10m
connection.ember-csi.io/9b850b73-c149-464a-b6a8-79adea0184ca   19m
connection.ember-csi.io/dc42c8ad-5290-4481-8022-2f9f05b754ef   16m
connection.ember-csi.io/ef80a942-f532-412d-8711-017a4cf400a7   5m45s

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
