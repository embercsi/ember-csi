#!/usr/bin/env bash
set -e

cd /vagrant
make lint
make unit-tests
travis-scripts/setup-lvm.sh
make centos-bm-lvm

exit
