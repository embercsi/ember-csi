#!/usr/bin/env bash

set -e

yum -y update
yum install -y epel-release git gcc python-devel lvm2 docker
systemctl start docker.service

curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"
python get-pip.py
pip install --upgrade pip
