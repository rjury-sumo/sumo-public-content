# From Sumo Logic Collector Docker Image
# but taken out install
# provides good container to test installer scripts
# see https://github.com/SumoLogic/sumologic-collector-docker/blob/main/Dockerfile.arm64

FROM ubuntu:20.04
LABEL maintainer="Sumo Logic <docker@sumologic.com>"

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update --quiet && \
 apt-get install -y --no-install-recommends apt-utils && \
 apt-get upgrade --quiet --allow-downgrades --allow-remove-essential --allow-change-held-packages -y && \
 apt-get install --quiet --allow-downgrades --allow-remove-essential --allow-change-held-packages -y wget 
#  wget -q -O /tmp/collector.deb https://collectors.sumologic.com/rest/download/deb/64 && \
#  dpkg -i /tmp/collector.deb && \
#  rm /tmp/collector.deb && \
# need curl for our installer
 #apt-get install -y curl
RUN apt install -y curl
# nice to look round
RUN apt install -y vim

RUN apt-get clean --quiet && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY *.sh /
COPY sources/sumo-sources.json.tmpl /etc/sumo-sources.json.tmpl

ENTRYPOINT ["/bin/bash"]