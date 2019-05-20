FROM centos:7
ARG RELEASE
ARG VERSION
ARG BUILD_DATE
ARG VCS_REF
ARG TAG

LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>" \
      openstack_release=${RELEASE} \
      version=${VERSION} \
      description="Ember CSI Plugin" \
      org.label-schema.schema-version="1.0" \
      org.label-schema.name="ember-csi" \
      org.label-schema.version=${TAG}  \
      org.label-schema.description="Ember CSI Plugin" \
      org.label-schema.url="https://ember-csi.io" \
      org.label-schema.build-date=${BUILD_DATE} \
      org.label-schema.vcs-url="https://github.com/embercsi/ember-csi" \
      org.label-schema.vcs-ref=${VCS_REF}

# Enable RPDB debugging on this container by default
ENV PYTHONUNBUFFERED=true

# This is the default port, but if we change it via CSI_ENDPOINT then this will
# no longer be relevant.
# For the Master version expose RPDB port to support remote debugging
EXPOSE 50051 4444

RUN yum -y install --setopt=skip_missing_names_on_install=False targetcli iscsi-initiator-utils device-mapper-multipath epel-release lvm2 which && \
    yum -y install --setopt=skip_missing_names_on_install=False python2-pip pywbem python2-kubernetes centos-release-openstack-${RELEASE} && \
    yum -y install --setopt=skip_missing_names_on_install=False python-cinderlib xfsprogs e2fsprogs btrfs-progs nmap-ncat && \
    # We need to upgrade pyasn1 because the package for RDO is not new enough for
    # pyasn1_modules, which is used by some of the Google's libraries
    pip install --no-cache-dir --upgrade 'pyasn1<0.5.0,>=0.4.1' future "ember-csi==${TAG}" && \
    # Install driver specific RPM dependencies
    yum -y install --setopt=skip_missing_names_on_install=False python-rbd ceph-common pyOpenSSL && \
    # Install driver specific PyPi dependencies
    pip install --no-cache-dir krest purestorage pyxcli && \
    yum clean all && \
    rm -rf /var/cache/yum

# Define default command
CMD ["ember-csi"]
