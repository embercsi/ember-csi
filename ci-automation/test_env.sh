#!/usr/bin/env bash

# Values: start|end
command=$1

if [[ "$command" = "start" ]]; then
	docker build -t lioramilbaum/ubuntu .
	docker run -it --privileged=true -v $(pwd)/../:/root/ember-csi lioramilbaum/ubuntu
elif [[ "$command" = "end" ]]; then
	docker rm $(docker ps -aq)
	docker rmi $(docker images -q)
fi
