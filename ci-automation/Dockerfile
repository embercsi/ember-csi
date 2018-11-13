FROM hrishikesh/libvirtd

RUN yum -y install rsync openssh-clients libvirt-client libxslt-devel libxml2-devel libvirt-devel libguestfs-tools-c ruby-devel gcc \
&& yum -y install https://releases.hashicorp.com/vagrant/2.2.0/vagrant_2.2.0_x86_64.rpm \
&& vagrant box add centos/7 --provider libvirt \
&& vagrant plugin install vagrant-libvirt
