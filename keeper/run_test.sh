#!/usr/bin/env bash
set -e

BUILD_TAG='build'
TEST_IMAGE=keeper_tests:${BUILD_TAG}

docker build -t ${TEST_IMAGE} --build-arg BUILDTAG=${BUILD_TAG} -f keeper/Dockerfile_tests .

echo "Pycodestyle tests>>>"
docker run -i --rm ${TEST_IMAGE} \
    bash -c "uv --project keeper run pycodestyle --exclude=.venv --max-line-length=120 keeper"
echo "<<<Pycodestyle tests"

echo "Pylint tests>>>"
docker run -i --rm ${TEST_IMAGE} bash -c \
    "uv --project keeper run pylint --rcfile=.pylintrc --fail-under=8 --fail-on=E,F ./keeper"
echo "<<<Pylint tests"

echo "Unit tests>>>"
docker run -i --rm ${TEST_IMAGE} bash -c \
    "uv --project keeper run python -m unittest discover ./keeper/report_server/tests"
echo "<<Unit tests"

docker rmi ${TEST_IMAGE}
