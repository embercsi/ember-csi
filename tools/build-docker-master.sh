#!/usr/bin/env bash
docker build -t akrog/ember-csi:master -f Dockerfile-master $1 .
