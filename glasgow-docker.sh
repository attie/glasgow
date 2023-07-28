#!/bin/bash
set -eu

image="docker.agsys.io/attie/glasgow:latest"
cache_volume="glasgow-cache"

#src_dir=".../path/to/glasgow/repo"

if [ ${#} -eq 1 ] && [ "${1}" == "pull" ]; then
	docker pull "${image}"
	exit $?
fi

args=()
args+=( run --rm -it --privileged )
args+=( -v /dev/bus/usb:/dev/bus/usb )
args+=( -v ${cache_volume}:/home/user/.cache/GlasgowEmbedded )

if [ "${PWD}" == "${src_dir:-}" ]; then
	args+=( -v "${PWD}:/opt/glasgow/" )
fi

if [ ${#} -eq 1 ] && [ "${1}" == "--help" ]; then
	cat <<-EOF >&2
	NOTE: You are using glasgow-in-docker, some things might not work as you'd expect (like
	      USB hotplug support)... The following basic modes are also available to you:

	  ${0##*/} pull         : retrieve an update docker image
	  ${0##*/} cache-clear  : remove the cache volume
	  ${0##*/} bash         : enter a shell inside a new container

	---
	EOF
	args=( run --rm "${image}" "${@}" )

elif [ ${#} -eq 1 ] && [ "${1}" == "pull" ]; then
	args=( pull "${image}" )

elif [ ${#} -eq 1 ] && [ "${1}" == "cache-clear" ]; then
	echo "Removing volume '${cache_volume}'..." >&2
	args=( volume rm "${cache_volume}" )

elif [ ${#} -eq 1 ] && [ "${1}" == "bash" ]; then
	args+=( --entrypoint '' "${image}" "${@}" )

else
	# normal operation
	args+=( "${image}" "${@}" )
fi

docker "${args[@]}"
exit ${?}
