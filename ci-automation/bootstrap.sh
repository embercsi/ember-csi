#!/usr/bin/env bash

set -e

home=$( dirname "${BASH_SOURCE[0]}" )

# Install RDO trunk repositories to install cinderlib from RPMs
curl -o /etc/yum.repos.d/rdo-trunk-runtime-deps.repo https://trunk.rdoproject.org/centos7-master/rdo-trunk-runtime-deps.repo
curl -o /etc/yum.repos.d/delorean.repo https://trunk.rdoproject.org/centos7-master/current/delorean.repo

PKGS=(epel-release)
yum install --setopt=skip_missing_names_on_install=False -y "${PKGS[@]}"
PKGS=(git gcc python-devel lvm2 docker python2-pip e2fsprogs iscsi-initiator-utils python2-kubernetes python-cinderlib)
yum install --setopt=skip_missing_names_on_install=False -y "${PKGS[@]}"

systemctl start docker.service iscsid.service

pip install -r $home/requirements_dev.txt
pip install -e $home/..
