ARG CONTROL_IMAGE=python:3.12-slim-bookworm
FROM ${CONTROL_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server sshpass \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT []
CMD ["/usr/sbin/sshd", "-D", "-e"]
