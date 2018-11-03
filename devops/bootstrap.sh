#!/usr/bin/env bash

yum -y update
yum install -y git gcc python-devel lvm2 docker
systemctl start docker.service

curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"
python get-pip.py
pip install --upgrade pip

git clone https://github.com/Akrog/ember-csi.git
cd ember-csi

make lint
make unit-tests
travis-scripts/setup-lvm.sh
make ubuntu-lvm
