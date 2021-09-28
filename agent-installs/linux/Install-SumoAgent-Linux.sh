#!/bin/bash

# SUMO AGENT INSTALL SCRIPT
# There are several ways to install the sumo agent on linux.
# We used to use the command line installer. with recent ubuntu this has been having some issues to do with 32 bit.cat /etc/os-release
# for sumo's info see: https://help.sumologic.com/03Send-Data/Installed-Collectors/04Install-a-Collector-on-Linux

# Linux 64: https://collectors.us2.sumologic.com/rest/download/linux/64
# Linux Debian: https://collectors.us2.sumologic.com/rest/download/deb/64
# Linux RPM: https://collectors.us2.sumologic.com/rest/download/rpm/64
# Mac OS: https://collectors.us2.sumologic.com/rest/download/macos
# Tarball: https://collectors.us2.sumologic.com/rest/download/tar
# Windows 32: https://collectors.us2.sumologic.com/rest/download/windows
# Windows 64: https://collectors.us2.sumologic.com/rest/download/win64

# INSTALL APPROACH
# We are installing sumo but NOT REGISTERING using VskipRegistration
# the agent will not start and later scripts should setup user.properties and json source config before registration
# this is a good approach as you can put the install script in an image such as AMI and add other config later.

if cat /etc/os-release | grep debian; then
    echo "running dpkg installer..."
    wget -q -O /tmp/collector.deb https://collectors.us2.sumologic.com/rest/download/deb/64
    dpkg -i /tmp/collector.deb
elif cat /etc/os-release | grep 'Amazon Linux'; then
    echo "running rpm installer..."
    wget -q -O /tmp/collector.rpm https://collectors.us2.sumologic.com/rest/download/rpm/64
    yum localinstall /tmp/collector.rpm -y
else
    echo "running command line installer"
    curl -s https://collectors.us2.sumologic.com/rest/download/linux/64 -o SumoCollector-Latest.sh
    chmod +x SumoCollector-Latest.sh
    ./SumoCollector-Latest.sh -q -Vsumo.accessid=SETLATER -Vsumo.accesskey=SETLATER -VskipRegistration=true -Vephemeral=true -Vcollector.url=https://collectors.us2.sumologic.com -VdisableScriptSource=true
    rm SumoCollector-Latest.sh
fi

#echo "By default the Collector will be installed in either /opt/SumoCollector or /usr/local/SumoCollector."
echo "The agent you have installed is ready to be packaged in an image."
echo "You still have two steps to go to have a fully working agent:"
echo " - configure user.properties "
echo " - configure json sources"
echo " - start agent service so it can register"