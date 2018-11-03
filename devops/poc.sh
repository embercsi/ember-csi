#!/usr/bin/env bash

command=$1
step=$2

if [[ "$command" = "start" ]]; then
	if [[ "$step" = "1" ]]; then
		vagrant up
	elif [[ "$step" = "2" ]]; then
		docker build -t rhdp/ubuntu .
		docker run -it --privileged=true -v ~/.vagrant.d:/root/.vagrant.d rhdp/ubuntu cd /var/tmp;vagrant up
	#	docker run -it --privileged -v /var/run/libvirt:/var/run/libvirt rhdp/libvirt
	fi
elif [[ "$command" = "end" ]]; then
	#statements
	if [[ "$step" = "1" ]]; then
		vagrant destroy --force
	elif [[ "$step" = "2" ]]; then
		docker rm $(docker ps -aq)
		docker rmi $(docker images -q)
	fi
fi

# eval $(minishift oc-env)
#
# if [ "$command" = "start" ]; then
# 	oc login -u developer -p developer https://192.168.42.191:8443
# 	oc get projects/ember-csi > /dev/null 2>&1
# 	if [ "$?" == "1" ]; then
# 		oc new-project ember-csi
# 	fi
# 	oc new-app kubevirt/libvirt:latest
# else
# 	oc login -u developer -p developer https://192.168.42.191:8443
# 	oc delete project ember-csi
# fi
