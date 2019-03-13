#!/usr/bin/env bash
set -ev
truncate -s 10G /root/ember-volumes
lo_dev=`losetup --show -f /root/ember-volumes`
vgcreate ember-volumes $lo_dev
vgscan
