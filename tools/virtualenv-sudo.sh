#!/usr/bin/env bash

# Script to ensure that calling commands added in the virtualenv with sudo will
# be able to find them during the functional tests, ie: cinder-rtstool

params=()
for arg in "$@"; do params+=("\"$arg\""); done
params="${params[@]}"
# sudo -E --preserve-env=PATH /bin/bash -c "$params"
sudo -E PATH=$PATH /bin/bash -c "$params"
