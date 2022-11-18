#!/bin/bash

shopt -s expand_aliases

if [ -z "$1" ] || [ -z "$2" ]
then
    echo "- Missing mandatory argument:"
    echo " - Usage: source pre_test.sh <SDE_INSTALL_PATH> <IPDK_RECIPE>"
    return 0
fi

export SDE_INSTALL=$1
export IPDK_RECIPE=$2

echo "Killing qemu"
pkill -9 qemu

echo "killing infrap4d"
pkill -9 infrap4d

echo "sleeping for 2 seconds"
sleep 2

echo "removing any vhost users from /tmp"
rm -rf /tmp/vhost-user-*
rm -rf /tmp/intf/vhost-user-*

echo "setting PATH"
export PATH=$PATH:$IPDK_RECIPE/install/bin

echo "sleeping for 5 seconds"
sleep 5

export LD_LIBRARY_PATH=$IPDK_RECIPE/install/lib/:$SDE_INSTALL/lib:$SDE_INSTALL/lib64

