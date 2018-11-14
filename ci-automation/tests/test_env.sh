#!/usr/bin/env bash

on_exit() {
    echo "$?"
		vagrant destroy --force
    exit
}

command=$1
export VAGRANT_VAGRANTFILE=ci-automation/tests/Vagrantfile

if [[ "$command" = "up" ]]; then
	vagrant up --provider=libvirt
	trap 'on_exit' SIGTERM SIGINT SIGHUP
elif [[ "$command" = "destroy" ]]; then
	vagrant destroy --force
else
	vagrant $command
fi

exit
