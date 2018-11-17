# CI Automation

Vagrantfile               - Used for spinning testing env (VM) via Vagrantfile which runs the tests
tests.sh                  - The tests which are run on the testing env
testing_env_main.sh       - Main script to spin up/destroy the testing env (VM inside a running container)
requirements.txt          - Python module dependencies for the testing env
Dockerfile                - Container which runs the testing env VM
testing_env_up.sh         - A script which spins the testing env
bootstrap.sh              - A script which bootstraps the testing env
tests/                    - Testing the CI automation
