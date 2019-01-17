#!/usr/bin/env bash
docker run --env-file rbd -t --privileged --net=host \
    -v /dev:/dev  \
    -v `realpath ../../tmp/mnt`:/mnt \
    -v `realpath ../../tmp`:/var/lib/cinder  \
    -v `realpath ./ceph.conf`:/etc/ceph/ceph.conf \
    -v `realpath ./ceph.client.cinder.keyring`:/etc/ceph/ceph.client.cinder.keyring \
    -p 50051:50051 -p 4444:4444 --name=ember-csi --rm=true embercsi/ember-csi
