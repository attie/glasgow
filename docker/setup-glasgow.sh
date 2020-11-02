#!/bin/bash -eu

git clone https://github.com/GlasgowEmbedded/glasgow.git /opt/glasgow -b master
cd /opt/glasgow/software

python3 setup.py develop

glasgow -V
