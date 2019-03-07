#!/usr/bin/env bash
set -e

cleanup()
{
  echo "Cleaning up"
  pkill -6 ember-csi
  echo "Done cleanup... quitting"
}

trap cleanup EXIT

home=$( dirname "${BASH_SOURCE[0]}" )
sudo $home/bootstrap.sh

cd "$home/.."
echo "-------------------- unit-tests --------------------"
make unit-tests
echo "-------------------- setup-lvm  --------------------"
sudo tools/setup-lvm.sh
echo "-------------------- bm-lvm     --------------------"
make centos-bm-lvm
echo "-------------------- done       --------------------"
