#!/usr/bin/env bash
set -e

home=$( dirname "${BASH_SOURCE[0]}" )
sudo $home/bootstrap.sh

cd "$home/.."
echo "-------------------- unit-tests --------------------"
make unit-tests
echo "-------------------- setup-lvm  --------------------"
sudo travis-scripts/setup-lvm.sh
echo "-------------------- bm-lvm     --------------------"
make centos-bm-lvm
echo "-------------------- done       --------------------"

pkill -6 ember-csi
