FROM ubuntu:18.04

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update \
&& apt-get install -y vim rsync virtualbox wget openssh-server \
&& wget -c https://releases.hashicorp.com/vagrant/2.2.0/vagrant_2.2.0_x86_64.deb \
&& dpkg -i vagrant_2.2.0_x86_64.deb \
&& vagrant box add centos/7 --provider virtualbox

WORKDIR /root/ember-csi
ENV VAGRANT_VAGRANTFILE automation/Vagrantfile
CMD ["vagrant", "up" ]
