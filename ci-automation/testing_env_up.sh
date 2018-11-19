#!/usr/bin/env bash

set -e

echo "Spin testing env - begin"
cd /root/ember-csi/ci-automation
vagrant up --provider libvirt
echo "Spin testing env - end"
