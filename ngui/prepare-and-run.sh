#!/bin/sh -eu

WORKDIR="/usr/src/app"
UI_PATH="${WORKDIR}/ui"
SERVER_PATH="${WORKDIR}/server"

function initializeEnvironmentVariables(){
    echo "window.optscale = window.optscale || {};";
    for i in `env | grep '^VITE'`
    do
        key=$(echo "$i" | cut -d"=" -f1);
        val=$(echo "$i" | cut -d"=" -f2);
        echo "window.optscale.${key}='${val}' ;";
    done
}

initializeEnvironmentVariables > ${UI_PATH}/build/config.js

# updating script include version in html file, to drop client browser cache
current_timestamp=`date +%s`
sed -i ${UI_PATH}/build/index.html -e "s/\${buildVersion}/${current_timestamp}/" ${UI_PATH}/build/index.html

# running application
cd ${SERVER_PATH}/dist
node server.js