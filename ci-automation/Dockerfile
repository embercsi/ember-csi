FROM centos:7

RUN yum install -y openssh-clients rsync qemu libvirt libvirt-devel ruby-devel gcc qemu-kvm \
&& yum clean all \
&& yum install -y https://releases.hashicorp.com/vagrant/2.2.0/vagrant_2.2.0_x86_64.rpm \
&& vagrant box add centos/7 --provider libvirt \
&& vagrant plugin install vagrant-libvirt

WORKDIR /root/ember-csi
ENV VAGRANT_VAGRANTFILE ci-automation/Vagrantfile
CMD ["vagrant", "up", "--provider", "libvirt" ]
