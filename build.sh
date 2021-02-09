#!/usr/bin/env bash
set -e
set -x

DOCKER_REPO='docker.io/embercsi/ember-csi'

GIT_TAG=`git describe --all`
PY_VERSION=`grep "VENDOR_VERSION = " ember_csi/constants.py | sed -r "s/^VENDOR_VERSION = '(.+)'/\1/"`

# Tagged releases
if [[ ${GIT_TAG} == tags/* ]]; then
  if [[ "${GIT_TAG}" != "tags/${PY_VERSION}" ]]; then
    echo "Tag '${GIT_TAG}' doesn't match 'tags/${PY_VERSION}' from python code"
    exit 1
  fi

  EMBER_VERSION=`echo ${GIT_TAG} | cut -d/ -f2`
  BRANCH=`cat hooks/rdo-releases`
  DOCKER_FILE='Dockerfile-release'
  CONTAINER_TAG='stable'

# Branches and master
elif [[ "${GIT_TAG}" == heads/* ]]; then
  DOCKER_FILE='Dockerfile'
  EMBER_VERSION=$(echo "${PY_VERSION}.dev`date +%d%m%Y%H%M%S%N`")
  CONTAINER_TAG=`echo ${GIT_TAG} | cut -c7-`
  BRANCH='master'

# If it's a feature branch
else
  echo "Unknown git HEAD, it's not a tag, nor master, nor a feature branch"
  exit 2
fi

IMAGE_NAME=${DOCKER_REPO}:${CONTAINER_TAG}

MSG="uilding $IMAGE_NAME\n Branch: $BRANCH\n Git tag: $GIT_TAG\n Ember version: $EMBER_VERSION"
echo -e "B$MSG"

CACHE_DIR="`pwd`/cache/${CONTAINER_TAG}"

mkdir -p $CACHE_DIR/{pip,wheel,git_code}
sudo podman build \
         --build-arg RELEASE=$BRANCH \
         --build-arg VERSION=$EMBER_VERSION \
         --build-arg BUILD_DATE=`date -u +"%Y-%m-%dT%H:%M:%SZ"` \
         --build-arg VCS_REF=`git rev-parse --short HEAD` \
         -t $IMAGE_NAME \
         -v $CACHE_DIR:/var/cache:rw,shared,z \
         -f $DOCKER_FILE .

echo -e "Finished b$MSG"
