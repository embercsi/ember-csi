#!/usr/bin/env bash

# Assume we are running the example from a dev environment, so activate virtual
# environment to satisfy requirements.
if [[ ! -v VIRTUAL_ENV ]]; then
    tox -epy27 --notest
    . ../../.tox/py27/bin/activate
fi

# Set configuration via environmental variables
. ./$1

# Run the CSI driver service
cinderlib-csi

exit_code=$?

rm -rf tmp groups

exit $exit_code
