# Ember-CSI master and latest images
# Ember uses current master
# Cinder, cinderlib, and os-brick projects no longer support Python 2, so there
# are no RDO rpms for Python 2 on Centos 7 and Python 3 packages are only for
# Centos 8, so we install things from pypi and source code.
#
# Uses master repository from Ember-CSI, cinderlib, os-brick, and Cinder.
#
# The multi-stage Docker build requires using podman instead of docker in order
# to user overlay mounts.
#
# Cinderlib and Cinder:
#  - Pull from master if RELEASE=master
#  - Pull from RELEASE if RELEASE!=master
#
# sudo podman build -v `pwd`/tmp/cache-7:/var/cache:rw,shared,z -t embercsi/ember-csi:3 -f Dockerfile-3 . 2>&1 | tee tmp/result.txt
#
# We don't clean the yum or dnf cache because it should be an external mount
#
# =============================================================================
#  First stage: Build and cache packages
# =============================================================================
FROM centos:7 AS wheeler
ARG RELEASE=master
ARG VERSION=master
ARG PIP_CACHE=/var/cache/pip
ARG WHEEL_CACHE=/var/cache/wheel
ARG CODE_CACHE=/var/cache/git_code
LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>" \
      description="Cinder, cinderlib, and ember-csi package builder"

RUN yum -y install epel-release which git && \
    yum -y install python3 python3-pip python3-wheel python3-devel gcc gcc-c++ openssl-devel && \
    mkdir -p $PIP_CACHE $WHEEL_CACHE $CODE_CACHE && \
    # First install non dev packages
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE krest purestorage pyxcli python-3parclient python-lefthandclient pyOpenSSL python-lefthandclient pyOpenSSL && \
    # Centos 7 can't build newer grpcio, so force it here
    # https://forums.cpanel.net/threads/unable-to-install-grpc-via-pecl.685069/
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE grpcio==1.15.0

RUN cd $CODE_CACHE && \
    if [[ ! -d os-brick ]]; then git clone --branch ${RELEASE} https://opendev.org/openstack/os-brick; else (cd os-brick && git remote update && git checkout ${RELEASE}); fi && \
    if [[ ! -d cinder ]]; then git clone --branch ${RELEASE} https://opendev.org/openstack/cinder; else (cd cinder && git remote update&& git checkout ${RELEASE}); fi && \
    if [[ ! -d cinderlib ]]; then git clone --branch ${RELEASE} https://opendev.org/openstack/cinderlib; else (cd cinderlib && git remote update && git checkout ${RELEASE}); fi && \

    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE --constraint=https://releases.openstack.org/constraints/upper/${RELEASE} -r os-brick/requirements.txt && \
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE os-brick && \

    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE --constraint=https://releases.openstack.org/constraints/upper/${RELEASE} -r cinder/requirements.txt && \
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE cinder && \

    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE --constraint=https://releases.openstack.org/constraints/upper/${RELEASE} -r cinderlib/requirements.txt && \
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE cinderlib

COPY . /ember-csi

# Add build metadata (date and time when the container was generated) to the
# version reported by Ember-CSI following semver notation:
# https://semver.org/#spec-item-10
# TODO: Maybe use pbr instead of doing it manually
RUN rm $CODE_CACHE/* || true && \
    cp /ember-csi/nsenter-commands/* $CODE_CACHE && \
    sed -i -r "s/^VENDOR_VERSION = '(.+)'/VENDOR_VERSION = '$VERSION'/" /ember-csi/ember_csi/constants.py && \
    sed -i -r "s/version='(.+)'/version='$VERSION'/" /ember-csi/setup.py && \
    sed -i -r "s/^__version__ = '(.*)'$/__version__ = '$VERSION'/" /ember-csi/ember_csi/__init__.py && \
    cd /ember-csi && python3 setup.py csi_proto && \
    rm $WHEEL_CACHE/ember_csi* && \
    # As explained earlier we need to pin the grpcio library
    pip3 wheel --cache-dir=$PIP_CACHE --find-links=$WHEEL_CACHE --wheel-dir=$WHEEL_CACHE grpcio==1.15.0 /ember-csi/

# =============================================================================
# Second stage: Install Ember-CSI
# =============================================================================

FROM centos:7
ARG RELEASE=master
ARG VERSION=master
ARG BUILD_DATE
ARG VCS_REF
ARG TAG
ARG PIP_CACHE=/var/cache/pip
ARG WHEEL_CACHE=/var/cache/wheel
ARG CODE_CACHE=/var/cache/git_code

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
RUN sed -i 's/keepcache=0/keepcache=1/g' /etc/yum.conf && \
    yum -y install lsscsi targetcli epel-release lvm2 which && \
    yum -y install python3 python3-pip && \
    yum -y install xfsprogs e2fsprogs btrfs-progs nmap-ncat && \
    # Install driver specific RPM dependencies
    curl --silent --remote-name --location https://github.com/ceph/ceph/raw/octopus/src/cephadm/cephadm && \
    chmod +x cephadm && \
    # Create the ceph repo for the ceph packages
    ./cephadm add-repo --release nautilus && \
    yum -y install python3-rbd ceph-common && \
    rm ./cephadm && \
    # Required to apply patches
    yum -y install patch && \
    # Install driver specific PyPi dependencies
    pip3 install --cache-dir=$PIP_CACHE --no-index --find-links=$WHEEL_CACHE krest purestorage pyxcli python-3parclient python-lefthandclient pyOpenSSL && \
    pip3 install --pre --cache-dir=$PIP_CACHE --no-index --find-links=$WHEEL_CACHE ember-csi && \
    cp `find ${CODE_CACHE} -maxdepth 1 -type f` /usr/local/sbin

# Define default command
CMD ["ember-csi"]
