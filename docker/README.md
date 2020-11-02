# Glasgow Docker Container

## Build

The `Dockerfile` and setup scripts will download the toolchain, and setup Glasgow.

```bash
docker build -t glasgow .
```

## Run

The entrypoint is set to `glasgow`, meaning that if you just want to use the Glasgow utility, you can simply run the container with the relevant subcommand:

```bash
docker run --rm -it --privileged -v /dev/bus/usb:/dev/bus/usb/ glasgow list
```

If you want to do something more complex inside the container, then you can override the entrypoint like this:

```bash
docker run --rm -it --privileged -v /dev/bus/usb:/dev/bus/usb/ --entrypoint bash glasgow
```
