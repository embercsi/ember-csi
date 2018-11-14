#!/usr/bin/env bash

echo "Container UP - start"
cd /root/ember-csi/ci-automation
vagrant up --provider libvirt
echo "Container UP - end"

exit
