FROM alpine:latest

RUN apk add bash jq alpine-sdk libusb-dev python3-dev py3-pip \
	&& pip3 install --upgrade pip

COPY setup-toolchain.sh /opt/
RUN /opt/setup-toolchain.sh

COPY setup-nmigen.sh /opt/
RUN /opt/setup-nmigen.sh

COPY setup-glasgow.sh /opt/
RUN /opt/setup-glasgow.sh

ENTRYPOINT [ "glasgow" ]
