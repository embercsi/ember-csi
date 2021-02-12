# OpenShift example

Please refer to the [installation documentation](https://docs.ember-csi.io/en/latest/installation.html) for details on how to install Ember-CSI with the operator on an existing OpenShift deployment.

If you don't have an OpenShift cluster already deployed, then the easiest way to see Ember-CSI in action is probably using the *testing script*, which deploys a single node OpenShift cluster inside a VM (using [CRC](https://developers.redhat.com/products/codeready-containers/overview)) and then uses the Ember-CSI operator to deploy and LVM driver.

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
