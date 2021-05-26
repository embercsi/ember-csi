# Ember-CSI master and latest images
# Ember uses current master
# Cinderlib and Cinder:
#  - Pull from master if RELEASE=master
#  - Pull from RELEASE if RELEASE!=master
FROM quay.io/centos/centos:stream8
ARG RELEASE=master
ARG VERSION=master
ARG BUILD_DATE
ARG VCS_REF
ARG PIP_CACHE=/var/cache/pip
ARG WHEEL_CACHE=/var/cache/wheel

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
RUN echo 'keepcache=true' >> /etc/dnf/dnf.conf && \
    dnf -y install targetcli epel-release lvm2 which && \
    dnf -y install python3-pip python3-kubernetes python3-pywbem && \
    dnf -y install xfsprogs e2fsprogs nmap-ncat && \
    mkdir -p $PIP_CACHE $WHEEL_CACHE && \
    # Install the RDO repository
    if [ "$RELEASE" = "master" ]; then curl -o /etc/yum.repos.d/rdo-trunk-runtime-deps.repo https://trunk.rdoproject.org/centos8-master/rdo-trunk-runtime-deps.repo; curl -o /etc/yum.repos.d/delorean.repo https://trunk.rdoproject.org/centos8-master/current/delorean.repo; else yum -y install centos-release-openstack-${RELEASE}; fi && \
    # Enable PowerTools so we can access python3-httplib2
    sed -i -r 's/^enabled=0/enabled=1/' /etc/yum.repos.d/CentOS-Stream-PowerTools.repo && \
    dnf -y install python3-cinderlib python3-grpcio protobuf && \
    # Create the ceph repo for the ceph packages
    curl --silent --remote-name --location https://github.com/ceph/ceph/raw/octopus/src/cephadm/cephadm && \
    chmod +x cephadm && \
    ./cephadm add-repo --release octopus && \
    yum -y install python3-rbd ceph-common && \
    rm ./cephadm && \
    dnf -y install python3-pyOpenSSL && \
    # Required to apply patches
    dnf -y install patch && \
    # Install driver specific PyPi dependencies
    pip3 install --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE krest purestorage pyxcli python-3parclient python-lefthandclient

COPY . /ember-csi

# Add build metadata (date and time when the container was generated) to the
# version reported by Ember-CSI following semver notation:
# https://semver.org/#spec-item-10
# TODO: Maybe use pbr instead of doing it manually
RUN sed -i -r "s/^VENDOR_VERSION = '(.+)'/VENDOR_VERSION = '$VERSION'/" /ember-csi/ember_csi/constants.py && \
    sed -i -r "s/version='(.+)'/version='$VERSION'/" /ember-csi/setup.py && \
    sed -i -r "s/^__version__ = '(.*)'$/__version__ = '$VERSION'/" /ember-csi/ember_csi/__init__.py && \
    pip3 install --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE -ve /ember-csi && \
    # Merge nsenter-commands directory structure with the root directory
    cd /ember-csi/nsenter-commands && \
    find ./ ! \( -type d \) -printf '%P\n' | xargs -n 1 -I {} mv '{}' '/{}'

# Define default command
CMD ["ember-csi"]
