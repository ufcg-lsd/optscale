#!/usr/bin/env bash

# ./build.sh [component] [tag] [-r registry] [-u username] [-p password] [--no-cache] [--use-nerdctl]
# leave registry empty if default registry [docker.io] used

# Initialize default values
COMPANY="hystax"
REGISTRY=""
LOGIN=""
PASSWORD=""
COMPONENT=""
INPUT_TAG=""
FLAGS=""
NO_CACHE=false
USE_NERDCTL=false
BUILD_TOOL="docker"

# Parse command line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -r) REGISTRY="$2"; shift ;;
        -u) LOGIN="$2"; shift ;;
        -p) PASSWORD="$2"; shift ;;
        --no-cache) NO_CACHE=true ;;
        --use-nerdctl) USE_NERDCTL=true ;;
        *)
            # Check if COMPONENT is empty
            if [[ -z "$COMPONENT" ]]; then
                COMPONENT="$1"
            else
                # If COMPONENT is already set, then set BUILD_TAG
                INPUT_TAG="$1"
            fi
            ;;
    esac
    shift
done

# Set build tool based on flag
if [[ "$USE_NERDCTL" == true ]]; then
    BUILD_TOOL="nerdctl"
fi

# Set --no-cache flag
if [[ "$NO_CACHE" == true ]]; then
    FLAGS="--no-cache"
fi

COMMIT_ID=$(git rev-parse --verify HEAD)

use_registry() {
  if [[ -n "${LOGIN}" && -n "${PASSWORD}" ]]; then
    true
  else
    false
  fi
}

BUILD_TAG=${INPUT_TAG:-'local'}
FIND_CMD="find . -mindepth 2 -maxdepth 3 -print | grep Dockerfile | grep -vE '(test|.j2)'"
FIND_CMD="${FIND_CMD} | grep $COMPONENT/"

if use_registry; then
  echo "$BUILD_TOOL login"
  $BUILD_TOOL login ${REGISTRY} -u "${LOGIN}" -p "${PASSWORD}"
fi

retag() {
  if use_registry; then
    if [ -z $3 ]; then
      if $BUILD_TOOL pull "${COMPANY}/$1:${COMMIT_ID}"; then
        $BUILD_TOOL tag "${COMPANY}/$1:${COMMIT_ID}" "$1:$2"
        return 0
      else
        return 1
      fi
    else
      if $BUILD_TOOL pull "$3/$1:${COMMIT_ID}"; then
        $BUILD_TOOL tag "$3/$1:${COMMIT_ID}" "$1:$2"
        return 0
      else
        return 1
      fi
    fi
  fi
  return 1
}

push_image () {
   echo "Pushing $1:$2"
    if [ -z $3 ]; then
      $BUILD_TOOL tag "$1:$2" "$COMPANY/$1:$2"
      $BUILD_TOOL tag "$1:$2" "$COMPANY/$1:$COMMIT_ID"
      $BUILD_TOOL push "$COMPANY/$1:$2"
      $BUILD_TOOL push "$COMPANY/$1:$COMMIT_ID"
    else
      $BUILD_TOOL tag "$1:$2" "$3/$1:$2"
      $BUILD_TOOL tag "$1:$2" "$3/$1:$COMMIT_ID"
      $BUILD_TOOL push "$3/$1:$2"
      $BUILD_TOOL push "$3/$1:$COMMIT_ID"
    fi
}

for DOCKERFILE in $(eval ${FIND_CMD} | xargs)
do
    COMPONENT=$(echo "${DOCKERFILE}" | awk -F '/' '{print $(NF-1)}')
    retag  $COMPONENT $BUILD_TAG $REGISTRY
    if [ "$?" -eq 0 ]; then
      echo "component $COMPONENT re-tagged $COMMIT_ID -> $BUILD_TAG"
    else
      echo "Building image for ${COMPONENT}, build tag: ${BUILD_TAG}"
      $BUILD_TOOL build $FLAGS -t ${COMPONENT}:${BUILD_TAG} -f ${DOCKERFILE} .
    fi

    if use_registry; then
      push_image $COMPONENT $BUILD_TAG $REGISTRY
    fi
done
