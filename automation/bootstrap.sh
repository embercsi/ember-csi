#!/usr/bin/env bash

set -e

PKGS="epel-release git gcc python-devel lvm2 docker"
yum install -y $PKGS
systemctl start docker.service
yum install -y python2-pip
