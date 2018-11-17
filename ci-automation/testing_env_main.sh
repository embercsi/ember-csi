#!/usr/bin/env bash

homedir=`dirname "${0}"`
command=$1

on_destroy() {
  rm -rf /var/tmp/CentOS-Dockerfiles
  docker rm -f centos-test-env
  sudo rm -rf $homedir/.vagrant/machines/default/libvirt
}

on_exit() {
    echo "$?"
    on_destroy
    sudo rm -rf $homedir/.vagrant/machines/default/libvirt
    exit
}

build_images() {
  pushd /var/tmp
  # cloning private account repo till PR is approved and merged
  #git clone https://github.com/CentOS/CentOS-Dockerfiles.git
  git clone https://github.com/lioramilbaum/CentOS-Dockerfiles.git
  cd CentOS-Dockerfiles/systemd/centos7
  docker build -t centos/systemd .
  cd ../../libvirtd/centos7
  docker build -t centos/libvirtd .
  popd
  docker build -t centos-test-env .
}

on_up() {
    trap 'on_exit' SIGTERM SIGINT SIGHUP EXIT
  	build_images
  	docker run -d --privileged -d -e 'container=docker' \
  		-v $(pwd)/../:/root/ember-csi \
  		--name centos-test-env centos-test-env
  	docker exec -i centos-test-env /root/ember-csi/ci-automation/testing_env_up.sh
}

if [[ "$command" = "up" ]]; then
  on_up
elif [[ "$command" = "destroy" ]]; then
  on_destroy
fi
