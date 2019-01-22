#!/usr/bin/env bash
set -e

cleanup()
{
  echo "Cleaning up"
  pkill -6 ember-csi
  echo "Done cleanup... quitting"
}

home=$( dirname "${BASH_SOURCE[0]}" )
sudo $home/bootstrap.sh

cd "$home/.."
echo "-------------------- unit-tests --------------------"
make unit-tests || { cleanup; exit 1; }
echo "-------------------- setup-lvm  --------------------"
sudo travis-scripts/setup-lvm.sh || { cleanup; exit 1; }
echo "-------------------- bm-lvm     --------------------"
make centos-bm-lvm || { cleanup; exit 1; }
echo "-------------------- done       --------------------"

cleanup
