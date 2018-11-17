#!/usr/bin/env bash

yum install -y docker git
rpm -V --nomode docker
systemctl start docker.service
cd /vagrant/ci-automation
./testing_env_main.sh up

exit
