#!/usr/bin/env bash
# =======================================================================
# Sidecar 启动脚本
# 必备环境变量：
#   UPSTREAM_SOCKS5_HOST  上游 socks5 主机
#   UPSTREAM_SOCKS5_PORT  上游 socks5 端口
#   UPSTREAM_SOCKS5_USER  上游用户名（可选）
#   UPSTREAM_SOCKS5_PASS  上游密码（可选）
# 挂载约定：
#   /flows      该 run 的 mitmproxy flow 输出目录
#   /ca         持久化的 mitmproxy CA 目录（首次启动后由 sidecar 落盘）
# =======================================================================
set -euo pipefail

: "${UPSTREAM_SOCKS5_HOST:?UPSTREAM_SOCKS5_HOST required}"
: "${UPSTREAM_SOCKS5_PORT:?UPSTREAM_SOCKS5_PORT required}"
UPSTREAM_USER="${UPSTREAM_SOCKS5_USER:-}"
UPSTREAM_PASS="${UPSTREAM_SOCKS5_PASS:-}"

log() { echo "[sidecar $(date +%H:%M:%S)] $*"; }

# ---------- 1) proxychains 配置：mitmproxy 出站走上游 socks5 ----------
cat > /etc/proxychains4.conf <<EOF
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 ${UPSTREAM_SOCKS5_HOST} ${UPSTREAM_SOCKS5_PORT} ${UPSTREAM_USER} ${UPSTREAM_PASS}
EOF

# ---------- 2) 准备 mitmproxy CA（从持久卷恢复或首次生成） ----------
mkdir -p /root/.mitmproxy /ca
if [ -f /ca/mitmproxy-ca.pem ]; then
  log "Restoring CA from /ca"
  cp /ca/mitmproxy-ca.pem /root/.mitmproxy/
  cp /ca/mitmproxy-ca-cert.pem /root/.mitmproxy/ 2>/dev/null || true
fi

# ---------- 3) 启动 mitmdump（先于 hev，避免 tun 转发到未就绪端口） ----------
mkdir -p /flows
FLOW_FILE="/flows/$(date +%Y%m%d-%H%M%S).flow"
log "Starting mitmdump (socks5 inbound :8080, upstream via proxychains -> ${UPSTREAM_SOCKS5_HOST}:${UPSTREAM_SOCKS5_PORT})"
proxychains4 -q mitmdump \
  --mode socks5 \
  --listen-host 127.0.0.1 --listen-port 8080 \
  --save-stream-file "$FLOW_FILE" \
  -s /sidecar/recorder.py \
  >/var/log/mitmdump.log 2>&1 &
MITM_PID=$!

# 等 8080 端口就绪 + CA 生成
for i in $(seq 1 40); do
  if ss -ltn 2>/dev/null | grep -q ':8080 '; then break; fi
  sleep 0.25
done
for i in $(seq 1 20); do
  if [ -f /root/.mitmproxy/mitmproxy-ca-cert.pem ]; then break; fi
  sleep 0.25
done

# 持久化 CA
if [ -f /root/.mitmproxy/mitmproxy-ca-cert.pem ] && [ ! -f /ca/mitmproxy-ca-cert.pem ]; then
  log "Persisting newly generated CA to /ca"
  cp /root/.mitmproxy/mitmproxy-ca.pem /ca/ 2>/dev/null || true
  cp /root/.mitmproxy/mitmproxy-ca-cert.pem /ca/
fi

# ---------- 4) 创建 tun 设备 + 默认路由 ----------
log "Bringing up tun0 + default route"
ip tuntap add mode tun dev tun0
ip addr add 198.18.0.1/15 dev tun0
ip link set dev tun0 up
ip route add default dev tun0 metric 100 || true

# DNS：发到 198.18.0.1（在 tun 子网内）→ 被 hev 接管 → 走 socks5
echo "nameserver 198.18.0.1" > /etc/resolv.conf

# ---------- 5) hev 配置：tun 流量 → socks5 client → 127.0.0.1:8080 (mitm) ----------
cat > /etc/hev-socks5-tunnel.yml <<EOF
tunnel:
  name: tun0
  mtu: 8500
  ipv4: 198.18.0.1
socks5:
  port: 8080
  address: 127.0.0.1
  udp: 'tcp'
misc:
  task-stack-size: 20480
  log-file: /dev/null
  log-level: warn
EOF

log "Starting hev-socks5-tunnel"
hev-socks5-tunnel /etc/hev-socks5-tunnel.yml &
HEV_PID=$!

log "Sidecar up: mitmproxy=$MITM_PID hev=$HEV_PID flow=$FLOW_FILE"
wait
