#!/usr/bin/env bash
docker run --env-file xtremio -t --privileged --net=host \
    -v /etc/iscsi:/etc/iscsi \
    -v /dev:/dev \
    -v `realpath ../../tmp/mnt`:/mnt \
    -v `realpath ../../tmp`:/var/lib/cinder \
    -p 50051:50051 akrog/cinderlib-csi
