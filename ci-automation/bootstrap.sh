#!/usr/bin/env bash

set -e

PKGS="epel-release git gcc python-devel lvm2 docker"
yum install -y $PKGS
rpm -V --nomode $PKGS
systemctl start docker.service
yum install -y python2-pip
rpm -V python2-pip
pip install --upgrade -r /vagrant/ci-automation/requirements.txt
