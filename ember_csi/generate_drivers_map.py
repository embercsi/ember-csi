#!/usr/bin/env python
# Copyright (c) 2018, Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Program to generate simplified cinder mappings

import argparse
import json
import sys

import cinderlib


def main():
    def get_key(driver_name):
        if driver_name.lower().endswith('driver'):
            driver_name = driver_name[:-6]
        return driver_name

    parser = argparse.ArgumentParser(prog=sys.argv[0])
    parser.add_argument('-o', '--output', type=argparse.FileType('w'),
                        default=sys.stdout, help="Output file")
    parser.add_argument('-d', '--detailed', action="store_true")
    args = parser.parse_args()

    drivers = cinderlib.list_supported_drivers()

    if not args.detailed:
        drivers = [get_key(k) for k in sorted(drivers.keys())]
    else:
        drivers = {get_key(k): v for k, v in drivers.items()}

    result = json.dumps(drivers, sort_keys=True, indent=4)
    args.output.write(result)


if __name__ == '__main__':
    main()
