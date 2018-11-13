#!/usr/bin/env bash

# Values: start|end
command=$1

if [[ "$command" = "start" ]]; then
	docker build -t centos-test-env .
	docker run -d --privileged -d -e 'container=docker' \
		-v /sys/fs/cgroup:/sys/fs/cgroup:rw -v $(pwd)/../:/root/ember-csi \
		--name centos-test-env centos-test-env
	docker exec -i centos-test-env /root/ember-csi/ci-automation/container_up.sh
	sudo rm -rf .vagrant/machines
elif [[ "$command" = "end" ]]; then
	docker rm -f centos-test-env
fi
