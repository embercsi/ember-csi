#!/usr/bin/env bash

on_exit() {
    echo "$?"
		docker rm -f centos-test-env
    exit
}

command=$1

if [[ "$command" = "up" ]]; then
	docker build -t centos-test-env .
	docker run -d --privileged -d -e 'container=docker' \
		-v /sys/fs/cgroup:/sys/fs/cgroup:rw -v $(pwd)/../:/root/ember-csi \
		--name centos-test-env centos-test-env
	docker exec -i centos-test-env /root/ember-csi/ci-automation/container_up.sh
	sudo rm -rf .vagrant/machines
	trap 'on_exit' SIGTERM SIGINT SIGHUP
elif [[ "$command" = "destroy" ]]; then
	docker rm -f centos-test-env
fi

exit
