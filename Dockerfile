# Ember-CSI master image
#
# This image uses master repository from Ember-CSI, cinderlib, os-brick, and
# Cinder.
#
# It uses a multi-stage Docker build that requires a PyPi server to be running
# outside of the containers to pass the wheel packages from the first container
# to the final container.
#
# The embercsi/pypiserver container is built using tools/Dockerfile-pypiserver
#    docker build -t embercsi/pypiserver -f tools/Dockerfile-pypiserver .
#
# The build requires to run the server, do the build, and stop the server
#    docker run -d --rm --name pypiserver -p 12345:8080 embercsi/pypiserver
#    docker build -t embercsi/ember-csi:master -f Dockerfile-master --build-arg PIP_SERVER=192.168.1.7 --build-arg PIP_PORT=12345 .
#    sudo docker stop pypiserver
#
FROM centos:7
ARG PIP_SERVER
ARG PIP_PORT=8080

LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>" \
      description="Cinder, cinderlib, and ember-csi package builder"

RUN yum -y install epel-release which git && \
    yum -y install python2-pip python-wheel python-devel gcc openssl-devel pywbem && \
    pip install --no-cache-dir twine && \

    # Need new setuptools version or we'll get "SyntaxError: '<' operator not allowed in environment markers" when installing Cinder
    pip install 'setuptools>=38.6.0' && \

    # First install non dev packages
    pip wheel --no-cache-dir --wheel-dir=/dist cinderlib && \
    pip wheel --no-cache-dir --wheel-dir=/dist 'krest>=1.3.0' 'purestorage>=1.6.0' 'pyxcli>=1.1.5' 'pyOpenSSL>=1.0.0' && \

    git clone 'https://git.openstack.org/openstack/os-brick' && \
    git clone 'https://git.openstack.org/openstack/cinder' && \
    # Until we get cinderlib's RBD connector fixed we need this code
    # git clone 'https://git.openstack.org/openstack/cinderlib' && \
    git clone 'https://github.com/Akrog/cinderlib.git' && \

    pip wheel --no-cache-dir --wheel-dir=/dev-dist os-brick/ && \
    pip wheel --no-cache-dir --pre --find-links=/dev-dist --wheel-dir=/dev-dist cinder/ && \
    pip wheel --no-cache-dir --pre --find-links=/dev-dist --wheel-dir=/dev-dist cinderlib/ && \

    rm -rf os-brick && \
    rm -rf cinder && \
    rm -rf cinderlib && \

    yum -y remove python-devel gcc openssl-devel && \
    yum clean all && \
    rm -rf /var/cache/yum

# Copy Ember-csi from current directory
COPY . /ember-csi

RUN pip wheel --no-cache-dir --find-links=/dist --wheel-dir=/dev-dist ember-csi/ && \
    twine upload -u user -p password --repository-url http://${PIP_SERVER}:${PIP_PORT} /dist/* && \
    twine upload --skip-existing -u user -p password --repository-url http://${PIP_SERVER}:${PIP_PORT} /dev-dist/*

# =============================================================================

FROM centos:7
ARG VERSION=master

LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>" \
      description="Ember CSI Plugin" \
      version=${VERSION}

# Enable RPDB debugging on this container by default
ENV X_CSI_DEBUG_MODE=rpdb \
    PYTHONUNBUFFERED=true

# This is the default port, but if we change it via CSI_ENDPOINT then this will
# no longer be relevant.
# For the Master version expose RPDB port to support remote debugging
EXPOSE 50051 4444


RUN yum -y install targetcli iscsi-initiator-utils device-mapper-multipath epel-release lvm2 which && \
    yum -y install python2-pip pywbem python-rbd ceph-common && \
    yum -y install xfsprogs e2fsprogs btrfs-progs nmap-ncat && \
    # We need to upgrade pyasn1 because the package for RDO is not new enough for
    # pyasn1_modules, which is used by some of the Google's libraries
    pip install --no-cache-dir --upgrade 'pyasn1<0.5.0,>=0.4.1' future && \
    pip install --no-cache-dir `if [ "$VERSION" = "master" ] ; then echo '--pre'; else echo ''; fi` --index-url http://${PIP_SERVER}:${PIP_PORT}/simple --trusted-host ${PIP_SERVER} cinderlib krest purestorage pyxcli pyOpenSSL && \
    pip install --no-cache-dir --pre --index-url http://${PIP_SERVER}:${PIP_PORT}/simple --trusted-host ${PIP_SERVER} ember-csi && \
    yum clean all && \
    rm -rf /var/cache/yum

# Define default command
CMD ["ember-csi"]
