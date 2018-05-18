#!/usr/bin/env bash
docker build -t akrog/cinderlib-csi:master -f dockerfile/Dockerfile-master $1 .
