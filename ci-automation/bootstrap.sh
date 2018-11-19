#!/usr/bin/env bash

set -e

PKGS=(epel-release)
yum install -y "${PKGS[@]}"
rpm -V --nomode "${PKGS[@]}"
PKGS=(git gcc python-devel lvm2 docker python2-pip)
yum install -y "${PKGS[@]}"
rpm -V --nomode "${PKGS[@]}"
systemctl start docker.service
