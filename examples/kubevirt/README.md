# Ember-CSI on Kubevirt

To use the Ember-CSI plugin on Kubevirt we need to make changes to our deployment.

The easiest way to make the changes is to copy this kubevirt directory into a directory of the kubevirt repository, and run the `csi_up.sh` script from there after the cluster is up and running.

For now the example only supports single node deployments, and for convenience we are using a pod instead of a StatefulSet and DaemonSets and the permissions are too broad.

Given the following assumptions:

- This `kubevirt` directory is in `$cl_example`.
- We have modified `X_CSI_BACKEND_CONFIG` environmental variable in the `csi.yml` (example is for XtremIO).
- Our current working directory is `kubevirt` repository's root directory.
- We haven't created a kubevirt cluster yet.
- The csi_up.sh scripts targets kubevirt version 0.7

The following commands will create the cluster, make changes to the cluster to support CSI plugins, deploy the CSI plugin, create a PVC, and an app that uses the PVC:


```
make cluster-up
make cluster-sync

# Modify the cluster for CSI
csi/csi_up.sh

# Setup RBAC
cluster/kubectl.sh create -f csi/rbac.yml

# Setup the CSI driver
cluster/kubectl.sh create -f csi/csi.yml

# Create a PVC (creates a volume on the storage via the CSI plugin)
cluster/kubectl.sh create -f csi/pvc.yml

# Create an APP that uses the created volume
cluster/kubectl.sh create -f csi/app.yml
```

We can send GRPC commands to the CSI driver using the deployed csc container.

For example to list volumes you can do:

```
cluster/kubectl.sh exec -c csc -it csi-xtremio-pod csc controller list-volumes
```

The example above created a PVC using the ember-csi driver and attached to a 'dummy' application that allowed attaching and inspecting the PVC. To launch a VM with kubevirt, you will also need to create the CDI pod and create a PVC with the correct CDI annotations. Once that is created, you should be able to create a VMI object using the newly created ember-csi backed PVC to launch a VM with Kubevirt. For more information, follow the instructions in the ['Getting started with storage'](https://github.com/kubevirt/kubevirt/blob/master/docs/devel/storage.md) document in Kubevirt.
