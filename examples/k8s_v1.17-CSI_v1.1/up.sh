#!/bin/sh
set -e

lhost=${LIBVIRT_HOST:-''}
luser=${LIBVIRT_USER:-'root'}

provider=${1:-'libvirt'}

ln -s -f Vagrantfile.$provider Vagrantfile

LIBVIRT_HOST=$lhost LIBVIRT_USER=$luser vagrant up --provider=$provider --no-provision $@ \
    && LIBVIRT_HOST=$lhost LIBVIRT_USER=$luser vagrant provision
