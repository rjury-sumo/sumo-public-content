#!/bin/bash

#set -x 

FILE=${SUMO_USER_PROPERTIES:=/opt/SumoCollector/config/user.properties}
CONFIG_PATH=`dirname "$FILE"`

# if you installed the agent this should be there!
mkdir -p $CONFIG_PATH

# get id and key from params or using AWS SSM
if [ -n "$SUMO_ACCESS_ID" ] || [ -n "$SUMO_ACCESS_ID" ]; then
    echo "using overide SUMO_ACCESS_ID  and key $SUMO_ACCESS_ID"
else
    echo 'no key supplied generating from SSM'
    SUMO_ACCESS_ID="$(aws ssm get-parameters --names 'sumo.accessid' --with-decryption --region $Region | grep -Po '(?<="Value": ")[^"]*')"
    SUMO_ACCESS_KEY="$(aws ssm get-parameters --names 'sumo.accesskey' --with-decryption --region $Region | grep -Po '(?<="Value": ")[^"]*')"
fi

SUMO_DISABLE_SCRIPTS=${SUMO_DISABLE_SCRIPTS:=true}
SUMO_EPHEMERAL=${SUMO_EPHEMERAL:=true}
SUMO_GENERATE_USER_PROPERTIES=${SUMO_GENERATE_USER_PROPERTIES:=true}
SUMO_RECEIVER_URL=${SUMO_RECEIVER_URL:='https://collectors.us2.sumologic.com'}
SUMO_SOURCES_JSON=${SUMO_SOURCES_JSON:=/etc/sumo-sources.json}
SUMO_SYNC_SOURCES=${SUMO_SYNC_SOURCES:=true}

if [ -n "$SUMO_COLLECTOR_NAME" ]; then
  echo "You supplied SUMO_COLLECTOR_NAME $SUMO_COLLECTOR_NAME" 
else
    curl --max-time 3 http://169.254.169.254/latest/meta-data/ami-id 2>/dev/null 1>/dev/null
    if [ $? -eq 0 ]; then  
        # this demonstrates how you could dynamically construct a acme name standard name from aws metadata

        Region=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document | grep -Po '(?<="region" : ")[^"]*')
        InstanceId=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
        AWS_ACCOUNT_ID=`curl -s http://169.254.169.254/latest/dynamic/instance-identity/document|grep accountId|awk -F\" '{print $4}'`
        
        SUMO_COLLECTOR_NAME="$InstanceId+$AWS_ACCOUNT_ID+"

        if [[ "${SUMO_COLLECTOR_NAME}" == "+" ]] ;then
            echo "AWS name set failed default to hostname"
            SUMO_COLLECTOR_NAME=`hostname`
        fi
        echo "Generated SUMO_COLLECTOR_NAME $SUMO_COLLECTOR_NAME"
    else

        echo 'no sumo host name found going for default'
        SUMO_COLLECTOR_NAME="`hostname`"
    fi
fi

generate_user_properties_file() {
    if [ -z "$SUMO_ACCESS_ID" ] || [ -z "$SUMO_ACCESS_KEY" ]; then
      echo "FATAL: Please provide credentials, either via the SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables,"
      echo "       or as the first two command line arguments!"
      exit 1
    fi

    if [ "${SUMO_SYNC_SOURCES}" == "true" ]; then
        SUMO_SYNC_SOURCES=${SUMO_SOURCES_JSON}
        unset SUMO_SOURCES_JSON
    else
        unset SUMO_SYNC_SOURCES
    fi

    # Supported user.properties configuration parameters
    # More information https://help.sumologic.com/Send_Data/Installed_Collectors/stu_user.properties
    declare -A SUPPORTED_OPTIONS
    SUPPORTED_OPTIONS=(
        ["SUMO_ACCESS_ID"]="accessid"
        ["SUMO_ACCESS_KEY"]="accesskey"
        ["SUMO_RECEIVER_URL"]="url"
        ["SUMO_COLLECTOR_NAME"]="name"
        ["SUMO_SOURCES_JSON"]="sources"
        ["SUMO_SYNC_SOURCES"]="syncSources"
        ["SUMO_PROXY_HOST"]="proxyHost"
        ["SUMO_PROXY_PORT"]="proxyPort"
        ["SUMO_PROXY_USER"]="proxyUser"
        ["SUMO_PROXY_PASSWORD"]="proxyPassword"
        ["SUMO_PROXY_NTLM_DOMAIN"]="proxyNtlmDomain"
        ["SUMO_CLOBBER"]="clobber"
        ["SUMO_DISABLE_SCRIPTS"]="disableScriptSource"
        ["SUMO_JAVA_MEMORY_INIT"]="wrapper.java.initmemory"
        ["SUMO_JAVA_MEMORY_MAX"]="wrapper.java.maxmemory"
        ["SUMO_EPHEMERAL"]="ephemeral"
        ["SUMO_FIELDS"]="fields"
    )

    USER_PROPERTIES=""

    for key in "${!SUPPORTED_OPTIONS[@]}"
    do
        value=${!key}
        if [ -n "${value}" ]; then
            USER_PROPERTIES="${USER_PROPERTIES}${SUPPORTED_OPTIONS[$key]}=${value}\n"
        fi
    done

    if [ -n "${USER_PROPERTIES}" ]; then
        echo -e ${USER_PROPERTIES} > $FILE
    fi
}

# If the user didn't supply their own user.properties file, generate it
$SUMO_GENERATE_USER_PROPERTIES && {
    generate_user_properties_file
}

echo "###################  user.properties #########################"
grep -v key $FILE

echo "###################  SUMO env.vars  #########################"
env | grep SUMO | grep -v KEY

