#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

set -ev
. "$DIR/set-tags"

mkdir -p /tmp/csi
for tag_info_string in $TAGS; do
  IFS=';' read -a tag_info <<< "$tag_info_string"

  echo "testing ${tag_info[1]}"
  echo "X_CSI_PERSISTENCE_CONFIG=$X_CSI_PERSISTENCE_CONFIG"
  echo "X_CSI_BACKEND_CONFIG=$X_CSI_BACKEND_CONFIG"

  docker run --name ember -t --privileged --net=host \
    -e X_CSI_PERSISTENCE_CONFIG=$X_CSI_PERSISTENCE_CONFIG \
    -e X_CSI_BACKEND_CONFIG=$X_CSI_BACKEND_CONFIG \
    -e DM_DISABLE_UDEV=1 \
    -e PYTHONUNBUFFERED=0 \
    -v /tmp/csi:/tmp/csi \
    -v /etc/iscsi:/etc/iscsi \
    -v /dev:/dev \
    -v /etc/lvm:/etc/lvm \
    -v /var/lock/lvm:/var/lock/lvm \
    -v /lib/modules:/lib/modules:ro \
    -v /run:/run \
    -v /var/lib/iscsi:/var/lib/iscsi \
    -v /etc/localtime:/etc/localtime:ro \
    -v /root/cinder:/var/lib/cinder \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -p 50051:50051 \
    -d ${tag_info[1]}

  echo -e "\n\n Ember-CSI startup logs:"
  docker logs ember

  $DIR/csi-sanity-v2 --csi.endpoint=127.0.0.1:50051 --test.timeout 15m --ginkgo.v --ginkgo.progress

  docker rm -f  ember
done
