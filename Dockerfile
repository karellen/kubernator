FROM python:3.11-slim-bookworm

COPY target/dist/kubernator*/dist/*.whl /tmp

RUN pip install --no-input --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*

WORKDIR /root
ENTRYPOINT ["/usr/local/bin/kubernator"]
