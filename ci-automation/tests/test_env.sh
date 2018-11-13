#!/usr/bin/env bash

# Values: start|end
command=$1

if [[ "$command" = "start" ]]; then
	VAGRANT_VAGRANTFILE=ci-automation/tests/Vagrantfile \
		vagrant up --provider=libvirt
elif [[ "$command" = "end" ]]; then
	VAGRANT_VAGRANTFILE=ci-automation/tests/Vagrantfile \
		vagrant destroy --force
fi
