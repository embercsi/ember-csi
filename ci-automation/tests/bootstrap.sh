#!/usr/bin/env bash

yum install -y docker
rpm -V --nomode docker
systemctl start docker.service
cd /vagrant/ci-automation
./test_env.sh up

exit
