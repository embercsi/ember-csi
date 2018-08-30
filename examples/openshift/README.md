# Ember-CSI on OpenShift v3.11 with External Ceph Backend

To deploy Ember CSI on OpenShift v3.11, specifically for the example in this directory, the only requirement is have access to an external Ceph cluster. In other words, the openshift cluster nodes must be able to reach the external Ceph cluster via a keyring file and ceph.conf. Assuming that we have in our possession, the ceph.conf and ceph client keyring files, deploying Ember CSI is straightforward.

The ember-csi.yml file contains everything, except the ceph secret, required to stand up Ember CSI. It will create the namespace/project, SCC, Roles, Statefulset, Daemonset, etc.

### Installation

Ember CSI can be deployed using the following two commands:

- oc apply -f ember-csi.yml
- oc create secret generic ceph-secrets  --from-file=/path/to/ceph.conf --from-file=/path/to/keyring

Once everything is running, you should see the output of 'oc get all'

```
$ oc whoami
system:admin
$ oc apply -f ember-csi.yml
$ oc create secret generic ceph-secrets  --from-file=/path/to/ceph.conf --from-file=/path/to/keyring
$ oc get all
NAME                   READY     STATUS    RESTARTS   AGE
pod/csi-controller-0   3/3       Running   0          43s
pod/csi-node-2z4j7     2/2       Running   0          43s

NAME                      DESIRED   CURRENT   READY     UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
daemonset.apps/csi-node   2         1         1         1            1           <none>          43s

NAME                              DESIRED   CURRENT   AGE
statefulset.apps/csi-controller   1         1         43s

```

#### Create a PVC
Once the Ember deployment looks like its running, create the PVC and inspect it to see if its in 'Bound' state. If yes, create the dummy app pod to mount the PVC.

```
$ oc create -f pvc.yml 
persistentvolumeclaim/ember-csi-pvc created
$
$ oc get pvc
NAME            STATUS    VOLUME                 CAPACITY   ACCESS MODES   STORAGECLASS   AGE
ember-csi-pvc   Bound     pvc-e787615bac5011e8   1Gi        RWO            ember-csi-sc   7s
$  
$ oc create -f app.yml
pod/my-csi-app created
$  
$ oc get all
NAME                   READY     STATUS    RESTARTS   AGE
pod/csi-controller-0   3/3       Running   0          8m
pod/csi-node-2z4j7     2/2       Running   0          8m
pod/my-csi-app         1/1       Running   0          34s

NAME                      DESIRED   CURRENT   READY     UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
daemonset.apps/csi-node   2         1         1         1            1           <none>          8m

NAME                              DESIRED   CURRENT   AGE
statefulset.apps/csi-controller   1         1         8m

````

### Tear Down
To tear down everthing we've created here, we will uninstall everything in reverse. *Warning*: Deletion using ember-csi.yml will even remove the 'ember-csi' namespace/project.

```
$ oc delete -f app.yml 
pod "my-csi-app" deleted
$
$ oc delete -f pvc.yml 
persistentvolumeclaim "ember-csi-pvc" deleted
$
$ oc delete -f ember-csi.yml 
serviceaccount "ember-csi-controller-sa" deleted
serviceaccount "ember-csi-node-sa" deleted
securitycontextconstraints.security.openshift.io "ember-csi-scc" deleted
clusterrole.rbac.authorization.k8s.io "csi-controller-cr" deleted
clusterrolebinding.rbac.authorization.k8s.io "csi-controller-rb" deleted
statefulset.apps "csi-controller" deleted
clusterrole.rbac.authorization.k8s.io "csi-node-cr" deleted
clusterrolebinding.rbac.authorization.k8s.io "csi-node-rb" deleted
daemonset.apps "csi-node" deleted
storageclass.storage.k8s.io "ember-csi-sc" deleted
$
$
```
