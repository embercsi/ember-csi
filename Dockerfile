# Based on centos
FROM centos:7.4.1708
LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>"
LABEL description="Cinderlib CSI Plugin"

RUN yum -y install targetcli iscsi-initiator-utils device-mapper-multipath epel-release https://repos.fedorapeople.org/repos/openstack/openstack-pike/rdo-release-pike-1.noarch.rpm && yum -y install python2-pip centos-release-openstack-pike && yum -y install openstack-cinder python-rbd ceph-common xfsprogs e2fsprogs btrfs-progs && yum clean all && rm -rf /var/cache/yum && pip install --no-cache-dir --process-dependency-links cinderlib-csi 'krest>=1.3.0'

# This is the default port, but if we change it via CSI_ENDPOINT then this will
# no longer be relevant.
EXPOSE 50051

# Define default command
CMD ["cinderlib-csi"]
