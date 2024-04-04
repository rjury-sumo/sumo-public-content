#!/bin/bash

#set -x

# Sumo agent JSON source configuration script.
# For this method we assume:
# OPTION A 
# we hve a single json sources file in this image dir called 
# "${SUMO_SOURCES_JSON}.tmpl"
# this contains all the soruces required an 

# OPTION B
# - we are going to produce a DIRECTORY of files for sync sources
# - your image includes a /templates directory
# - each templated source file in the directory has name template.json.tmpl

# ENV SUBSTITUTION
# - within each file(S) above any ${var} is substituted with env vars of same name even if NULL.
#   provided that env var have fomrmat similar to this example
#       "category": "${ENVIRONMENT}/app/mycategory",


SUMO_SOURCES_JSON=${SUMO_SOURCES_JSON:=/etc/sumo-sources.json}
SUMO_USER_PROPERTIES=${SUMO_USER_PROPERTIES:=/opt/SumoCollector/config/user.properties}
SUMO_SYNC_SOURCES=${SUMO_SYNC_SOURCES:=false}
RESTARTAGENT=${RESTARTAGENT:=true}

generate_sources_file() {
    # allow for two possible behaviours
    # true: we allow creating sources from templates with no $ENVIRONMENT subsitutions
    # false: (default) unset or empty $ENVIRONMENT is regarded as a fatal error
    SUMO_ALLOW_EMPTY_ENVIRONMENT=${SUMO_ALLOW_EMPTY_ENVIRONMENT:=false}

    if [ "$SUMO_ALLOW_EMPTY_ENVIRONMENT" = false ] ; then
        if [ -z ${ENVIRONMENT+x} ]; then
        echo "FATAL ERROR: unset ENVIRONMENT is not allowed with SUMO_ALLOW_EMPTY_ENVIRONMENT=false. Fix empty environment variable.";
        exit 1;
        fi
    fi

    # Support using env as replacement within sources.
    # Gather all template files
    declare -a TEMPLATE_FILES
    # this would take all the files from ONE sources file
    if [ -r "${SUMO_SOURCES_JSON}.tmpl" ]; then
        TEMPLATE_FILES+=("${SUMO_SOURCES_JSON}.tmpl")
    fi

    # this would take all the files from a templates directory
    if [ -d "${SUMO_SOURCES_JSON}" ]; then
        for f in $(find ${SUMO_SOURCES_JSON} -name '*.tmpl'); do TEMPLATE_FILES+=(${f}); done
    fi

    for from in "${TEMPLATE_FILES[@]}"
    do
        # Replace all env variables and remove .tmpl extension
        to=${from%.*}
        echo "INFO: Replacing environment variables from ${from} into ${to}"
        ls -l $from

        echo "=== json file: $from ==="
        cat $from

        #ls -l $to
        echo > ${to}

        if [ $? -ne 0 ]; then
            echo "FATAL: unable to write to ${to}"
            exit 1
        fi

        OLD_IFS=$IFS
        IFS=$'\n'
        while read line; do
          line_escape_backslashes=${line//\\/\\\\\\\\}
          echo $(eval echo "\"${line_escape_backslashes//\"/\\\"}\"") >> ${to}
        done <${from}
        IFS=${OLD_IFS}

        echo "=== json file: $to ==="
        cat $to

    done
}

generate_sources_file

if [ ! -e "${SUMO_SOURCES_JSON}" ]; then
  echo "FATAL: Unable to find $SUMO_SOURCES_JSON - please make sure you include it in your image!"
  exit 1
fi

if $RESTARTAGENT; then
    printf 'Restarting the Sumo Agent...\n'
    service collector restart

    echo "your collector should register shortly as: `grep name $SUMO_USER_PROPERTIES`"
    echo "service collector status"
    echo "tail /opt/SumoCollector/logs/collector.log"
    echo "cat /opt/SumoCollector/config/user.properties"
    echo "to test the dummy log source in this demo try:"
    echo "echo \"\`date\` \`uname -a\` host=\`hostname\`\" > /tmp/dummy.log"
else
  printf "A restart wasn't requested. You'll need to restart the Sumo Agent for the config changes to take affect\n"
fi





