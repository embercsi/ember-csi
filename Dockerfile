# Ember-CSI master and latest images
# Ember uses current master
# Cinderlib and Cinder:
#  - Pull from master if RELEASE=master
#  - Pull from RELEASE if RELEASE!=master
FROM centos:7
ARG RELEASE=master
ARG VERSION=master
ARG BUILD_DATE
ARG VCS_REF
ARG TAG

LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>" \
      openstack_release=${RELEASE} \
      version=${VERSION} \
      description="Ember CSI Plugin" \
      org.label-schema.schema-version="1.0" \
      org.label-schema.name="ember-csi" \
      org.label-schema.description="Ember CSI Plugin" \
      org.label-schema.url="https://ember-csi.io" \
      org.label-schema.build-date=${BUILD_DATE} \
      org.label-schema.vcs-url="https://github.com/embercsi/ember-csi" \
      org.label-schema.vcs-ref=${VCS_REF}

# Enable RPDB debugging on this container by default
ENV X_CSI_DEBUG_MODE=rpdb \
    PYTHONUNBUFFERED=true

# This is the default port, but if we change it via CSI_ENDPOINT then this will
# no longer be relevant.
# For the Master version expose RPDB port to support remote debugging
EXPOSE 50051 4444

# We first check that we have access to the PyPi server
RUN yum -y install targetcli iscsi-initiator-utils device-mapper-multipath epel-release lvm2 which && \
    yum -y install python2-pip pywbem python2-kubernetes && \
    yum -y install xfsprogs e2fsprogs btrfs-progs nmap-ncat && \
    # We need to upgrade pyasn1 because the package for RDO is not new enough for
    # pyasn1_modules, which is used by some of the Google's libraries
    pip install --no-cache-dir --upgrade 'pyasn1<0.5.0,>=0.4.1' future && \
    # Install the RDO repository
    if [ "$RELEASE" = "master" ]; then curl -o /etc/yum.repos.d/rdo-trunk-runtime-deps.repo https://trunk.rdoproject.org/centos7-master/rdo-trunk-runtime-deps.repo; curl -o /etc/yum.repos.d/delorean.repo https://trunk.rdoproject.org/centos7-master/current/delorean.repo; else yum -y install centos-release-openstack-${RELEASE}; fi && \
    yum -y install python-cinderlib && \
    # Install driver specific RPM dependencies
    yum -y install python-rbd ceph-common pyOpenSSL && \
    # Install driver specific PyPi dependencies
    pip install --no-cache-dir krest purestorage pyxcli && \
    yum clean all && \
    rm -rf /var/cache/yum

COPY . /ember-csi

RUN pip install --no-cache-dir -e /ember-csi

# Define default command
CMD ["ember-csi"]
