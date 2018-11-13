#!/usr/bin/env bash

# Values: start|end
command=$1

if [[ "$command" = "start" ]]; then
	docker build -t ember-csi .
	docker run -d --privileged -d -e 'container=docker' \
		-v /sys/fs/cgroup:/sys/fs/cgroup:rw -v $(pwd)/../:/root/ember-csi \
		--name ember-csi-test ember-csi
	docker exec -i ember-csi-test /root/ember-csi/ci-automation/container_up.sh
elif [[ "$command" = "end" ]]; then
	docker rm -f $(docker ps -aq)
fi
