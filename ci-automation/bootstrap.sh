#!/usr/bin/env bash

set -e

home=$( dirname "${BASH_SOURCE[0]}" )

PKGS=(epel-release)
yum install --setopt=skip_missing_names_on_install=False -y "${PKGS[@]}"
PKGS=(git gcc python-devel lvm2 docker python2-pip e2fsprogs iscsi-initiator-utils)
yum install --setopt=skip_missing_names_on_install=False -y "${PKGS[@]}"
systemctl start docker.service iscsid.service
pip install --upgrade setuptools
pip install --upgrade -r $home/requirements.txt
pip install -r $home/requirements_dev.txt
pip install -e $home/..

