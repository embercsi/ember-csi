#!/usr/bin/env python
# -*- coding: utf-8 -*-

import glob
import os
import subprocess
import sys

import setuptools
from setuptools.command import develop
from setuptools.command import install
from setuptools.command import sdist


# Wheel only necessary on the host to publish to PyPi, not on the container
try:
    from wheel import bdist_wheel
except ImportError:
    bdist_wheel = None


PATCH_FILES = True
PATCH_FILE_NAMES = glob.glob('patches/*.patch')


def _patch_libraries():
    if not PATCH_FILES:
        return

    packages_dir = setuptools.__file__.rsplit(os.path.sep, 2)[0]
    print('Patching libraries in %s' % packages_dir)
    subprocess.check_call('patches/apply-patches ' + packages_dir, shell=True)


class CustomInstall(install.install):
    def run(self):
        _patch_libraries()
        install.install.run(self)


class CustomDevelop(develop.develop):
    def run(self):
        _patch_libraries()
        develop.develop.run(self)


class CustomSdist(sdist.sdist):
    def run(self):
        global PATCH_FILES
        PATCH_FILES = False
        sdist.sdist.run(self)


if not bdist_wheel:
    CustomBdist = None
else:
    class CustomBdist(bdist_wheel.bdist_wheel):
        def run(self):
            global PATCH_FILES
            PATCH_FILES = False
            bdist_wheel.bdist_wheel.run(self)


with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.md') as history_file:
    history = history_file.read()


requirements = [
    'cinderlib>=0.9.0',
    'grpcio>=1.15.0',
    # GRPCIO v1.12.0 has broken dependencies, so we include them here
    'protobuf>=3.5.0.post1',
    # For the CRD persistent metadata plugin
    'kubernetes>=7.0.0,<12.0.0',
    # If we install from PyPi we needed a newer setuptools because some
    # Kubernetes dependencies use version in format of 4.*
    # 'setuptools>=40.0.0',
]

# We can't use 'future ; python_version<"3.0"', because it requires setuptools
# version 36.2 or higher
if sys.version_info[0] < 3:
    requirements.append('future')


dependency_links = [
]

test_requirements = [
    # TODO: put package test requirements here
]

setuptools.setup(
    cmdclass={
        'sdist': CustomSdist,
        'bdist_wheel': CustomBdist,
        'install': CustomInstall,
        'develop': CustomDevelop,
    },
    name='ember-csi',
    version='0.9.1',
    description=("Multi-vendor CSI plugin supporting over 80 storage drivers"),
    long_description=readme + '\n---\n' + history,
    long_description_content_type='text/markdown',
    author="Gorka Eguileor",
    author_email='gorka@eguileor.com',
    url='https://github.com/akrog/ember-csi',
    packages=setuptools.find_packages(
        exclude=['tmp', 'tests*', 'examples', 'docs']),
    package_dir={'ember_csi': 'ember_csi'},
    include_package_data=True,
    dependency_links=dependency_links,
    install_requires=requirements,
    license="Apache Software License 2.0",
    data_files=[
        ('./', ['HISTORY.md', 'README.md']),
        ('./patches', ['patches/apply-patches'] + PATCH_FILE_NAMES),
    ],
    zip_safe=True,
    keywords='ember_csi',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        "Programming Language :: Python :: 3",
        'Programming Language :: Python :: 3.6',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    entry_points={
        'console_scripts': [
            'ember-csi=ember_csi.ember_csi:main',
            'ember-list-drivers=ember_csi.generate_drivers_map:main',
            'ember-liveness=ember_csi.liveness:main',
        ],
        'cinderlib.persistence.storage': [
            'crd = ember_csi.cl_crd:CRDPersistence',
        ],
    }
)
