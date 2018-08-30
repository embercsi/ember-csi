## Deploy Ember-CSI on OpenShift v3.11 with Ceph Backend

### Steps

#### Create Ember CSI controller statefulset and node daemonset
- oc apply -f ember-csi.yml
- oc create secret generic ceph-secrets  --from-file=/path/to/ceph.conf --from-file=/path/to/keyring
- oc apply -f pvc.yml

#### Test attachment in a dummy app
- oc apply -f app.yml
