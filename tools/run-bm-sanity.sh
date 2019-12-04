#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

set -ev

mkdir -p /tmp/csi

echo "X_CSI_PERSISTENCE_CONFIG=$X_CSI_PERSISTENCE_CONFIG"
echo "X_CSI_BACKEND_CONFIG=$X_CSI_BACKEND_CONFIG"

for version in v0.2 v0.3 v1.0 v1.1; do
  echo "Running CSI sanity $version on Ember-CSI"
  PYTHONUNBUFFERED=0 X_CSI_SPEC_VERSION=$version ember-csi &
  sleep 10
  $DIR/csi-sanity-$version --csi.endpoint=127.0.0.1:50051 --test.timeout 15m --ginkgo.v --ginkgo.progress
  pkill -6 ember-csi
done
