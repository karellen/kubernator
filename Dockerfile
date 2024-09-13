FROM python:3.12-slim-bookworm

COPY target/dist/kubernator*/dist/*.whl /tmp

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /root

RUN pip install --no-input /tmp/*.whl && \
    apt update && apt install git -y && \
    kubernator --pre-cache-k8s-client $(seq 19 29) && \
    pip cache purge && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/ && \
    rm -rf /tmp/*

ENTRYPOINT ["/usr/local/bin/kubernator"]
