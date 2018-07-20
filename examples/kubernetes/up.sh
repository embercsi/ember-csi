#!/bin/sh

lhost=${LIBVIRT_HOST:-''}
luser=${LIBVIRT_USER:-'root'}

LIBVIRT_HOST=$lhost LIBVIRT_USER=$luser vagrant up --provider=libvirt --no-provision $@ \
    && LIBVIRT_HOST=$lhost LIBVIRT_USER=$luser vagrant provision
