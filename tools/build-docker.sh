#!/usr/bin/env bash
cl_version=`grep 'current_version =' setup.cfg | sed 's/current_version = '//`
docker build -t akrog/cinderlib-csi:v$cl_version -t akrog/cinderlib-csi:latest -f dockerfile/Dockerfile .
