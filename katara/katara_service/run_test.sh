#!/usr/bin/env bash
set -e

BUILD_TAG='build'
TEST_IMAGE=katara_service_tests:${BUILD_TAG}

docker build -t ${TEST_IMAGE} --build-arg BUILDTAG=${BUILD_TAG} -f katara/katara_service/Dockerfile_tests .

echo "Pycodestyle tests>>>"
docker run -i --rm ${TEST_IMAGE} \
    bash -c "uv --project katara/katara_service run pycodestyle --exclude=.venv katara"
echo "<<<Pycodestyle tests"

echo "Pylint tests>>>"
docker run -i --rm ${TEST_IMAGE} \
    bash -c "uv --project katara/katara_service run pylint --rcfile=katara/katara_service/.pylintrc --fail-under=9 --fail-on=E,C,F ./katara"

echo "Alembic down revision tests>>>"
docker run -i --rm ${TEST_IMAGE} bash -c \
    "uv --project katara/katara_service run tools/check_alembic_down_revisions/check_alembic_down_revisions.py --alembic_versions_path katara/katara_service/alembic/versions"
echo "<<Alembic down revision tests"

echo "Unit tests>>>"
docker run -i --rm ${TEST_IMAGE} \
    bash -c "uv --project katara/katara_service run python -m unittest discover ./katara/katara_service/tests"
echo "<<Unit tests"

docker rmi ${TEST_IMAGE}
