# Installers
here are some installer scripts and a docker container to test them in.

You need an accessid and key generated from your sumo instance for a user with 'manage collectors' permission.

./Install-SumoAgent-Linux.sh
this installs sumo with no config (suitable also for using in an AMI image)

./Config-SumoAgent-Properties.sh
user.props.aws.simple.sh
these are both examples of configuring user.properties when launching instance with default values that can be overridden by setting env vars. 
includes examples of setting collector name from an env var, aws metadata or from tags.

./Config-SumoAgent-Sources.sh
This is a demo script to show how to start with a templated source.json file, replace some values then register sumo agent.

## docker test container
You can use this to spin up test agents and use the Install, and Config scripts.

```
docker build -t sumo_agent .

# with fields
export SUMO_FIELDS='owner=some-team@acme.com,team=my-team'
docker run -it -e SUMO_ACCESS_ID=$SUMO_ACCESS_ID -e SUMO_ACCESS_KEY=$SUMO_ACCESS_KEY -e SUMO_FIELDS -e ENVIRONMENT=test sumo_agent 

# no fields
docker run -it -e SUMO_ACCESS_ID=$SUMO_ACCESS_ID -e SUMO_ACCESS_KEY=$SUMO_ACCESS_KEY -e ENVIRONMENT=test sumo_agent 

# no fields using TOKEN
docker run -it -e SUMO_INSTALLATION_TOKEN=$SUMOLOGIC_INSTALLATION_TOKEN -e ENVIRONMENT=test sumo_agent 

# install the agent unregistered
./Install-SumoAgent-Linux.sh

# config user.properties
d=`date +%s` SUMO_COLLECTOR_NAME="docker-agent-$d" ./Config-SumoAgent-Properties.sh

# your agent will register on next start (service collector start)
# to setup templated sources and restart:
./Config-SumoAgent-Sources.sh
```