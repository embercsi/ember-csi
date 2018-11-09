#!/usr/bin/env bash

# Values: start|end
command=$1

if [[ "$command" = "start" ]]; then
	docker build -t ember-csi .
	docker run -it --privileged=true -v $(pwd)/../:/root/ember-csi \
		--net=host -v /var/lib/libvirt:/var/lib/libvirt \
		-v /var/run/libvirt:/var/run/libvirt ember-csi
elif [[ "$command" = "end" ]]; then
	docker run -it --privileged=true -v $(pwd)/../:/root/ember-csi \
		--net=host -v /var/lib/libvirt:/var/lib/libvirt \
		-v /var/run/libvirt:/var/run/libvirt ember-csi vagrant destroy -f
	docker rm -f $(docker ps -aq)
fi
