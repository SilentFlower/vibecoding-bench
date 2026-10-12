# 同一源码批次构建两个最终镜像，gateway 与 sender 共享 Rust 发送实现。
FROM node:22-bookworm-slim AS frontend
WORKDIR /source/cc2api/web
COPY cc2api/web/package.json cc2api/web/package-lock.json ./
RUN npm ci
COPY cc2api/web/ ./
RUN npm run build
WORKDIR /terminal
RUN npm pack xterm@5.3.0 && npm pack xterm-addon-fit@0.8.0 \
    && mkdir xterm fit \
    && tar -xzf xterm-5.3.0.tgz -C xterm --strip-components=1 \
    && tar -xzf xterm-addon-fit-0.8.0.tgz -C fit --strip-components=1

FROM rust:1.96.0-slim-bookworm AS backend
ENV CARGO_BUILD_JOBS=2 CARGO_HTTP_MULTIPLEXING=false CARGO_HTTP_TIMEOUT=60
WORKDIR /source/cc2api
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
COPY cc2api/Cargo.toml cc2api/Cargo.lock ./
COPY cc2api/craftls ./craftls
COPY cc2api/vendor ./vendor
COPY cc2api/src ./src
COPY --from=frontend /source/cc2api/web/dist ./web/dist
RUN cargo build --locked --release --bins

FROM python:3.12-slim-bookworm AS control
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY orchestrator/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY orchestrator/*.py ./
COPY topics.md /repo/topics.md
COPY images/worker/entrypoint.sh /opt/v3/worker.sh
COPY webui /webui
COPY --from=frontend /terminal/xterm/lib/xterm.js /webui/vendor/xterm.js
COPY --from=frontend /terminal/xterm/css/xterm.css /webui/vendor/xterm.css
COPY --from=frontend /terminal/xterm/LICENSE /webui/vendor/xterm-LICENSE
COPY --from=frontend /terminal/fit/lib/xterm-addon-fit.js /webui/vendor/xterm-addon-fit.js
COPY --from=frontend /terminal/fit/LICENSE /webui/vendor/xterm-addon-fit-LICENSE
RUN python -c "from pathlib import Path; p=Path('/webui/index.html'); s=p.read_text(); s=s.replace('https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css','vendor/xterm.css').replace('https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js','vendor/xterm.js').replace('https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js','vendor/xterm-addon-fit.js'); p.write_text(s)"
COPY --from=backend /source/cc2api/target/release/claude-code-gateway /app/claude-code-gateway
COPY --from=frontend /source/cc2api/web/dist /app/web/dist
COPY images/v3/control-entrypoint.sh /usr/local/bin/v3-control
RUN chmod 755 /usr/local/bin/v3-control
ARG V3_RELEASE
ARG V3_PARENT_REV
ARG V3_GATEWAY_REV
LABEL vibebench.product="v3" vibebench.role="control" vibebench.release=$V3_RELEASE \
    vibebench.parent-revision=$V3_PARENT_REV vibebench.gateway-revision=$V3_GATEWAY_REV \
    org.opencontainers.image.source="https://github.com/SilentFlower/vibecoding-bench" \
    org.opencontainers.image.revision=$V3_PARENT_REV
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/v3-control"]

FROM python:3.12-slim-bookworm AS account
ARG HEV_VERSION=2.15.0
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config git curl wget unzip \
    ca-certificates locales tmux jq ripgrep tini util-linux iproute2 iptables iputils-ping \
    proxychains4 unbound dnsutils procps \
    && sed -i -E 's/^# (en_US|ja_JP|ko_KR|de_DE|fr_FR)\.UTF-8 UTF-8/\1.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen && rm -rf /var/lib/apt/lists/*
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && groupadd --gid 1000 node && useradd --uid 1000 --gid node --create-home --shell /bin/bash node
RUN python3 -m venv /opt/mitm && /opt/mitm/bin/pip install --no-cache-dir mitmproxy==11.1.3
ENV PATH="/opt/mitm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RUN case "$(uname -m)" in x86_64) arch=x86_64;; aarch64) arch=arm64;; *) exit 1;; esac \
    && wget -q --timeout=30 --tries=3 -O /usr/local/bin/hev-socks5-tunnel "https://github.com/heiher/hev-socks5-tunnel/releases/download/${HEV_VERSION}/hev-socks5-tunnel-linux-${arch}" \
    && chmod 755 /usr/local/bin/hev-socks5-tunnel
COPY images/sidecar /sidecar
COPY images/account/init.py /usr/local/bin/v3-account-init
COPY images/account/network-context.py /usr/local/bin/v3-network-context
COPY images/account/cli-version.sh /usr/local/bin/v3-cli-version
COPY --from=backend /source/cc2api/target/release/account-sender /usr/local/bin/account-sender
RUN chmod 755 /usr/local/bin/v3-* && mkdir -p /workspaces /run/v3
WORKDIR /home/node
ARG V3_RELEASE
ARG V3_PARENT_REV
ARG V3_GATEWAY_REV
LABEL vibebench.product="v3" vibebench.role="account" vibebench.release=$V3_RELEASE \
    vibebench.parent-revision=$V3_PARENT_REV vibebench.gateway-revision=$V3_GATEWAY_REV \
    org.opencontainers.image.source="https://github.com/SilentFlower/vibecoding-bench" \
    org.opencontainers.image.revision=$V3_PARENT_REV
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/v3-account-init"]
