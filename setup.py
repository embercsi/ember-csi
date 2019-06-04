#!/usr/bin/env python
# -*- coding: utf-8 -*-

import setuptools

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.md') as history_file:
    history = history_file.read()

requirements = [
    'cinderlib>=0.9.0',
    'grpcio==1.15.0',
    # GRPCIO v1.12.0 has broken dependencies, so we include them here
    'protobuf>=3.5.0.post1',
    # For the CRD persistent metadata plugin
    'kubernetes>=7.0.0',
    # If we install from PyPi we needed a newer setuptools because some
    # Kubernetes dependencies use version in format of 4.*
    # 'setuptools>=40.0.0',
]

dependency_links = [
]

test_requirements = [
    # TODO: put package test requirements here
]

setuptools.setup(
    name='ember-csi',
    version='0.9.0',
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
    data_files=[('./', ['HISTORY.md', 'README.md'])],
    zip_safe=True,
    keywords='ember_csi',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
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
