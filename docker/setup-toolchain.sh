#!/bin/bash -eu

read os <<< "linux"
read arch < <( uname -m )

read url < <(
  curl -s "https://api.github.com/repos/open-tool-forge/fpga-toolchain/releases/latest" \
    | jq -r \
      --arg os "${os}" \
      --arg arch "${arch}" \
      '
        .assets[]
          | select(.name | contains($os + "_" + $arch))
          | select(.name | endswith(".tar.gz"))
          | .browser_download_url
      '
)

curl -sL "${url}" | gzip -d | tar -xv -C /opt/
ln -sv /opt/fpga-toolchain/bin/* /usr/bin/

yosys -V
nextpnr-ice40 -V
