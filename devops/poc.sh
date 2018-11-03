#!/usr/bin/env bash

# Values: start|end
command=$1

# Value: 1|2|3
step=$2

if [[ "$command" = "start" ]]; then
	if [[ "$step" = "1" ]]; then
		vagrant up
	elif [[ "$step" = "2" ]]; then
		docker build -t lioramilbaum/ubuntu .
		docker run -it --privileged=true -v ~/.vagrant.d:/root/.vagrant.d lioramilbaum/ubuntu
#	docker run -it --privileged -v /var/run/libvirt:/var/run/libvirt rhdp/libvirt
	elif [[ "$step" = "3" ]]; then
		eval $(minishift oc-env)
		oc login -u developer -p developer https://192.168.42.191:8443
		oc get projects/ember-csi > /dev/null 2>&1
		if [ "$?" == "1" ]; then
			oc new-project ember-csi
		fi
		oc new-app kubevirt/libvirt:latest
	fi
elif [[ "$command" = "end" ]]; then
	if [[ "$step" = "1" ]]; then
		vagrant destroy --force
	elif [[ "$step" = "2" ]]; then
		docker rm $(docker ps -aq)
		docker rmi $(docker images -q)
	elif [[ "$step" = "3" ]]; then
		eval $(minishift oc-env)
		oc login -u developer -p developer https://192.168.42.191:8443
		oc delete project ember-csi
	fi
fi
