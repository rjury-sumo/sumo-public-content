# From Sumo Logic Collector Docker Image
# but taken out install
# provides good container to test installer scripts

FROM ubuntu:18.04
MAINTAINER Sumo Logic <docker@sumologic.com>

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update --quiet && \
    apt-get install -y --no-install-recommends apt-utils && \
    apt-get upgrade --quiet --allow-downgrades --allow-remove-essential --allow-change-held-packages -y && \
    apt-get install --quiet --allow-downgrades --allow-remove-essential --allow-change-held-packages -y wget 

#  wget -q -O /tmp/collector.deb https://collectors.sumologic.com/rest/download/deb/64 && \
#  dpkg -i /tmp/collector.deb && \
#  rm /tmp/collector.deb && \
#  apt-get clean --quiet && \
#  rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ubuntu 18.04 fails with commandline installer unless:
#RUN dpkg --add-architecture i386
#RUN apt-get update
#RUN apt-get install -y libgtk2.0-0:i386 libidn11:i386 libglu1-mesa:i386

# need curl for our installer
RUN apt-get install -y curl

# nice to look round
RUN apt-get install -y vim
COPY *.sh /
COPY sources/sumo-sources.json.tmpl /etc/sumo-sources.json.tmpl

ENTRYPOINT ["/bin/bash"]