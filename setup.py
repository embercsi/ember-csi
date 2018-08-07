#!/usr/bin/env python
# -*- coding: utf-8 -*-

import setuptools

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.md') as history_file:
    history = history_file.read()

requirements = [
    'cinderlib>0.2.1',
    'grpcio==1.12.0',
    # GRPCIO v1.12.0 has broken dependencies, so we include them here
    'protobuf>=3.5.0.post1',
    # For the CRD persistent metadata plugin
    'kubernetes>=6.0.0,<7.0.0',
    # Needed because some Kubernetes dependencies use version in format of 4.*
    'setuptools==40.0.0',
]

dependency_links = [
    # From github until cinderlib's latest code is published in pip
    'git+https://github.com/akrog/cinderlib.git@master#egg=cinderlib-1',
]

test_requirements = [
    # TODO: put package test requirements here
]

setuptools.setup(
    name='ember-csi',
    version='0.0.2',
    description=("Multi-vendor CSI plugin supporting over 80 storage drivers"),
    long_description=readme + '\n---\n' + history,
    long_description_content_type='text/markdown',
    author="Gorka Eguileor",
    author_email='gorka@eguileor.com',
    url='https://github.com/akrog/ember-csi',
    packages=setuptools.find_packages(exclude=['tmp', 'tests*']),
    package_dir={'ember_csi': 'ember_csi'},
    include_package_data=True,
    dependency_links=dependency_links,
    install_requires=requirements,
    license="Apache Software License 2.0",
    zip_safe=False,
    keywords='ember_csi',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    entry_points={
        'console_scripts': ['ember-csi=ember_csi.ember_csi:main'],
        'cinderlib.persistence.storage': [
            'crd = ember_csi.cl_crd:CRDPersistence',
        ],
    }
)
