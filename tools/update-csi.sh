#!/usr/bin/env bash

# Downloads latest CSI specs protobuffer definition from Github into csi.proto
# and then updates csi_pb2.grpc.py and csi_pb2.py with it.
# Should be invoqued from this project's root directory.
curl -o csi.proto https://raw.githubusercontent.com/container-storage-interface/spec/master/csi.proto

if [[ ! -v VIRTUAL_ENV ]]; then
    tox -epy27 --notest
    . .tox/py27/bin/activate
fi

python -m grpc_tools.protoc --proto_path=. --grpc_python_out=./cinderlib_csi --python_out=./cinderlib_csi csi.proto
