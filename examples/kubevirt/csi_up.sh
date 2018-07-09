#!/usr/bin/env bash
_kubectl='cluster/kubectl.sh'
KUBEVIRT_NUM_NODES=${KUBEVIRT_NUM_NODES:-1}

function _ssh() {
  cluster/cli.sh ssh node$(printf "%02d" $1) -- sudo $2
}

# Kubelet must be allowed to create attachment resources for CSI
$_kubectl get -o yaml clusterroles/system:node | perl -0pe 's/volumeattachments\n  verbs:\n/volumeattachments\n  verbs:\n  - create\n  - list\n  - update\n  - watch\n  - patch\n  - delete\n/' | $_kubectl replace -f -


for i in $(seq 1 ${KUBEVIRT_NUM_NODES}); do
    # Setup iSCSI and multipath
    _ssh $i 'yum install -y iscsi-initiator-utils device-mapper-multipath'
    _ssh $i 'mpathconf --enable --with_multipathd y --user_friendly_names n --find_multipaths y'
    _ssh $i 'systemctl enable --now iscsid'
    _ssh $i 'systemctl restart multipathd'

    # Node authorization doesn't allow modifying resources from other nodes, so
    # we'll authorize nodes via RBAC
    node_name="node$(printf "%02d" ${i})"
    $_kubectl get -o yaml clusterrolebindings/system:node | sed 's/subjects: null/subjects:/' | perl -0pe "s/subjects:\n/subjects:\n- kind: User\n  name: system:node:$node_name\n  namespace: kube-system\n/" | $_kubectl replace -f -
done

for i in $(seq 1 ${KUBEVIRT_NUM_NODES}); do
    _ssh $i 'systemctl stop kubelet'
    # Disable LVM dm creation
    _ssh $i 'sed -in '\''1h;1!H;${g;s/devices {\n/devices {\n\tfilter = [ "r|.*\/|" ]\n\tglobal_filter = [ "r|.*\/|" ]/;p;}'\'' /etc/lvm/lvm.conf'

    # Only on master
    if [ "$i" = "1" ]; then
        # Stop API, Scheduler, and Controller containers
        _ssh $i 'docker stop $(sudo docker ps --filter "name=apiserver_kube|scheduler_kube|manager_kube" --format "{{.ID}}")'
        # Kubelet doesn't want to call NodeStage and NodePublish, force it
        _ssh $i 'sed -i "s/KUBELET_EXTRA_ARGS=/KUBELET_EXTRA_ARGS=--enable-controller-attach-detach=false /" /etc/systemd/system/kubelet.service.d/09-kubeadm.conf'
        # Remove the Node restriction, that prevents creating cluster wide
        # resources (attachment)
        _ssh $i 'sed -i -e "s/NodeRestriction,//" -e "s/--authorization-mode=Node,RBAC/--authorization-mode=RBAC/" /etc/kubernetes/manifests/kube-apiserver.yaml'
    fi
done

# Restart Kubelets: recreate API, Scheduler, and Controller nodes)
for i in $(seq 1 ${KUBEVIRT_NUM_NODES}); do
    _ssh $i 'systemctl daemon-reload'
    _ssh $i 'systemctl restart kubelet'
done
