#!/bin/bash -eu

git clone https://github.com/nmigen/nmigen.git /opt/nmigen -b master
cd /opt/nmigen

python3 setup.py develop
