## Deploy EMber CSI on OpenSHift v3.11 with Ceph Backend

### Steps

'''
oc new-project csi
oc adm policy add-scc-to-user privileged -n csi -z csi-node-sa
oc adm policy add-scc-to-user privileged -n csi -z csi-controller-sa

# Create Cinder files (ceph.conf and keyring) as a secret
oc create secret generic ceph-secrets  --from-file=/path/to/ceph.conf --from-file=/path/to/keyring

# Create Ember CSI Deployment
oc apply -f controller.yml
oc apply -f node.yml
oc apply -f storage-class.yml
oc apply -f pvc.yml

# Test whether attach works in a dummy app
oc apply -f app.yml


'''
