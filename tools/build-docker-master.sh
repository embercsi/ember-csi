#!/usr/bin/env bash
docker build -t akrog/cinderlib-csi:master -f Dockerfile-master $1 .
