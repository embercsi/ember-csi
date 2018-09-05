.PHONY: clean clean-test clean-pyc clean-build docs help
.DEFAULT_GOAL := help
define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts


clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

python-requirements:
	pip install -r requirements_dev.txt
	pip install -e .

lint: python-requirements ## check style with flake8
	flake8 ember_csi tests

unit-tests: python-requirements ## run tests quickly with the default Python
	unit2 discover -v -s tests/unit

test-all: ## run tests on every Python version with tox
	tox

ubuntu-bm-lvm:
	X_CSI_PERSISTENCE_CONFIG='{"storage":"memory"}' \
	X_CSI_BACKEND_CONFIG='{"target_protocol":"iscsi","iscsi_ip_address":"127.0.0.1","volume_backend_name":"lvm","volume_driver":"cinder.volume.drivers.lvm.LVMVolumeDriver","volume_group":"ember-volumes","target_helper":"lioadm"}' \
	X_CSI_EMBER_CONFIG='{"project_id":"io.ember-csi","user_id":"io.ember-csi","root_helper":"sudo","disable_logs":false,"debug":true,"request_multipath":false}' \
	travis-scripts/run-bm-sanity.sh

ubuntu-lvm:
	X_CSI_PERSISTENCE_CONFIG='{"storage":"memory"}' \
	X_CSI_BACKEND_CONFIG='{"target_protocol":"iscsi","iscsi_ip_address":"127.0.0.1","volume_backend_name":"lvm","volume_driver":"cinder.volume.drivers.lvm.LVMVolumeDriver","volume_group":"ember-volumes","target_helper":"lioadm"}' \
	X_CSI_EMBER_CONFIG='{"project_id":"io.ember-csi","user_id":"io.ember-csi","root_helper":"sudo","disable_logs":false,"debug":true,"request_multipath":false}' \
	travis-scripts/run-sanity.sh

coverage: ## check code coverage quickly with the default Python

		coverage run --source ember_csi setup.py test

		coverage report -m
		coverage html
		$(BROWSER) htmlcov/index.html

docs: ## generate Sphinx HTML documentation, including API docs
	rm -f docs/ember_csi.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ ember_csi
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

servedocs: docs ## compile the docs watching for changes
	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

test-package:
	python setup.py check -r -s

test-release: clean
	python setup.py sdist bdist_wheel
	twine upload -r pypitest dist/*

release: clean ## package and upload a release
	python setup.py sdist bdist_wheel
	twine upload -r pypi dist/*

dist: clean ## builds source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean ## install the package to the active Python's site-packages
	python setup.py install
