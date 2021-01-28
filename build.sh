#!/usr/bin/env bash
set -e
set -x

OS_VERSION=${1:-'8'}

DOCKER_REPO='docker.io/embercsi/ember-csi'
if [[ "${OS_VERSION}" == "8" ]]; then
  DOCKER_FILE='Dockerfile8'
else
  DOCKER_FILE='Dockerfile'
fi
# EMBER_VERSION=${EMBER_VERSION:-`git describe --tags`}
GIT_TAG=`git describe --all`
PY_VERSION=`grep "VENDOR_VERSION = " ember_csi/constants.py | sed -r "s/^VENDOR_VERSION = '(.+)'/\1/"`


if [[ "${GIT_TAG}" == "heads/master" ]]; then
  EMBER_VERSION=$(echo "${PY_VERSION}.dev`date +%d%m%Y%H%M%S%N`")
  BRANCH='master'

elif [[ "${GIT_TAG}" == "tags/${PY_VERSION}" ]]; then
  EMBER_VERSION=`echo ${GIT_TAG} | cut -d/ -f2`
  BRANCH=`cat hooks/rdo-releases`

else
  echo "Tag '${GIT_TAG}' doesn't match 'tags/${PY_VERSION}' from python code"
  exit 1
fi

CONTAINER_TAG="${BRANCH}${OS_VERSION}"

echo -e "BRANCH: ${BRANCH}\nGIT_TAG: ${GIT_TAG}\nEMBER_VERSION: ${EMBER_VERSION}"

# -Arg RELEASE=  VERSION=
#
mkdir -p cache/$OS_VERSION/{pip,wheel,git_code}
sudo podman build \
         --build-arg RELEASE=$BRANCH \
         --build-arg VERSION=$EMBER_VERSION \
         --build-arg BUILD_DATE=`date -u +"%Y-%m-%dT%H:%M:%SZ"` \
         --build-arg VCS_REF=`git rev-parse --short HEAD` \
         -t ${DOCKER_REPO}:${CONTAINER_TAG} \
         -v "`pwd`/cache/${OS_VERSION}:/var/cache:rw,shared,z" \
         -f $DOCKER_FILE .
