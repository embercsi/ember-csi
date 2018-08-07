## Deploy Ember-CSI on OpenShift v3.11 with Ceph Backend

### Steps

#### Create a project and appropriate privileges to the service accounts
- oc new-project csi
- oc adm policy add-scc-to-user privileged -n csi -z csi-node-sa
- oc adm policy add-scc-to-user privileged -n csi -z csi-controller-sa

#### Create Cinder files (ceph.conf and keyring) as a secret
- oc create secret generic ceph-secrets  --from-file=/path/to/ceph.conf --from-file=/path/to/keyring

#### Create Ember CSI controller statefulset and node daemonset
- oc apply -f controller.yml
- oc apply -f node.yml
- oc apply -f storage-class.yml
- oc apply -f pvc.yml

#### Test attachment in a dummy app
- oc apply -f app.yml
