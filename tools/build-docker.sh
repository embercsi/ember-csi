#!/usr/bin/env bash
cl_version=`grep 'current_version =' setup.cfg | sed 's/current_version = '//`
docker build -t akrog/ember-csi:v$cl_version -t akrog/ember-csi:latest -f Dockerfile .
