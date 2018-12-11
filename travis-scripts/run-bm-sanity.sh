#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

set -ev

mkdir -p /tmp/csi

echo "X_CSI_PERSISTENCE_CONFIG=$X_CSI_PERSISTENCE_CONFIG"
echo "X_CSI_BACKEND_CONFIG=$X_CSI_BACKEND_CONFIG"

PYTHONUNBUFFERED=0 ember-csi &

$DIR/csi-sanity-v0.2.0 --csi.endpoint=127.0.0.1:50051 --test.timeout 15m --ginkgo.v --ginkgo.progress
