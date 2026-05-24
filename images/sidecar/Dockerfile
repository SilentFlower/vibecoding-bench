# =======================================================================
# Sidecar 镜像：透明代理 + TLS MITM
# 链路：worker → tun(默认路由) → hev-socks5-tunnel → mitmproxy(socks5 in)
#       → TLS MITM 解密 + flow 记录 → proxychains 包装出站 → 上游 SOCKS5
# 需要：CAP_NET_ADMIN + /dev/net/tun（docker-compose 已设置）
# =======================================================================
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      iproute2 iptables iputils-ping \
      ca-certificates curl wget xz-utils \
      proxychains4 \
      tini \
    && rm -rf /var/lib/apt/lists/*

# mitmproxy（11+ 支持现代 HTTP/2、bracket paste 等）
RUN pip install --no-cache-dir mitmproxy==11.1.3

# hev-socks5-tunnel：tun → socks5 client 转发器
ARG HEV_VERSION=2.7.6
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
      x86_64)  bin="hev-socks5-tunnel-linux-x86_64";; \
      aarch64) bin="hev-socks5-tunnel-linux-arm64";; \
      *) echo "unsupported arch: $arch" >&2; exit 1;; \
    esac; \
    wget -q -O /usr/local/bin/hev-socks5-tunnel \
      "https://github.com/heiher/hev-socks5-tunnel/releases/download/${HEV_VERSION}/${bin}"; \
    chmod +x /usr/local/bin/hev-socks5-tunnel

WORKDIR /sidecar
COPY start.sh /sidecar/start.sh
COPY recorder.py /sidecar/recorder.py
RUN chmod +x /sidecar/start.sh

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--", "/sidecar/start.sh"]
