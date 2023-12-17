FROM python:3.11-slim-bookworm

COPY target/dist/kubernator*/dist/*.whl /tmp

ENV DEBIAN_FRONTEND=noninteractive
RUN pip install --no-input --no-cache-dir /tmp/*.whl && \
    apt update && apt install git -y && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/ && \
    rm -rf /tmp/*

WORKDIR /root
RUN kubernator --pre-cache-k8s-client $(seq 19 28)
ENTRYPOINT ["/usr/local/bin/kubernator"]
