#!/usr/bin/env python
# -*- coding: utf-8 -*-

import setuptools

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'cinderlib',
    'grpcio==1.12.0',
    # GRPCIO v1.12.0 has broken dependencies, so we include them here
    'protobuf>=3.5.0.post1',
]

dependency_links = [
    # From github until cinderlib persistence is published in pip
    'git+https://github.com/akrog/cinderlib.git@persistence#egg=cinderlib-1',
]

test_requirements = [
    # TODO: put package test requirements here
]

setuptools.setup(
    name='cinderlib-csi',
    version='0.0.1',
    description=("CSI driver supporting all Cinder drivers without needing to "
                 "run any additional services like RabbitMQ, MariaDB, or "
                 "Cinder service"),
    long_description=readme + '\n\n' + history,
    author="Gorka Eguileor",
    author_email='gorka@eguileor.com',
    url='https://github.com/akrog/cinderlib-csi',
    packages=setuptools.find_packages(exclude=['tmp', 'tests*']),
    package_dir={'cinderlib_csi': 'cinderlib_csi'},
    include_package_data=True,
    dependency_links=dependency_links,
    install_requires=requirements,
    license="Apache Software License 2.0",
    zip_safe=False,
    keywords='cinderlib_csi',
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
        'console_scripts': ['cinderlib-csi=cinderlib_csi.cinderlib_csi:main'],
    }
)
