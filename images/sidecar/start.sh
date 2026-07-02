#!/usr/bin/env bash
# =======================================================================
# Sidecar 启动脚本
# 必备环境变量：
#   UPSTREAM_PROXY_SCHEME 上游代理协议：http / socks5 / socks5h（默认 socks5）
#   UPSTREAM_SOCKS5_HOST  上游代理主机（历史变量名，继续兼容）
#   UPSTREAM_SOCKS5_PORT  上游代理端口（历史变量名，继续兼容）
#   UPSTREAM_SOCKS5_USER  上游用户名（可选）
#   UPSTREAM_SOCKS5_PASS  上游密码（可选）
# 挂载约定：
#   /flows      该 run 的 mitmproxy flow 输出目录
#   /ca         持久化的 mitmproxy CA 目录（首次启动后由 sidecar 落盘）
# =======================================================================
set -euo pipefail

: "${UPSTREAM_SOCKS5_HOST:?UPSTREAM_SOCKS5_HOST required}"
: "${UPSTREAM_SOCKS5_PORT:?UPSTREAM_SOCKS5_PORT required}"
UPSTREAM_PROXY_SCHEME="${UPSTREAM_PROXY_SCHEME:-socks5}"
UPSTREAM_PROXY_SCHEME="${UPSTREAM_PROXY_SCHEME,,}"
UPSTREAM_USER="${UPSTREAM_SOCKS5_USER:-}"
UPSTREAM_PASS="${UPSTREAM_SOCKS5_PASS:-}"

log() { echo "[sidecar $(date +%H:%M:%S)] $*"; }

# ---------- 1) proxychains 配置：mitmproxy 出站走上游代理 ----------
case "$UPSTREAM_PROXY_SCHEME" in
  http)
    PROXYCHAINS_TYPE="http"
    ;;
  socks5|socks5h)
    # proxychains 负责目标域名代理解析；socks5h 在当前透明代理链路中等价为 socks5 出站。
    PROXYCHAINS_TYPE="socks5"
    ;;
  https)
    log "FATAL: https upstream proxy is not supported; use http:// or socks5://"
    exit 1
    ;;
  *)
    log "FATAL: unsupported UPSTREAM_PROXY_SCHEME=$UPSTREAM_PROXY_SCHEME"
    exit 1
    ;;
esac

# proxychains4 在 strict_chain + ProxyList 首条 时,host 字段必须是 IP,
# 不接受 hostname(会以 "invalid value or is not numeric" 拒启)。
# 上游代理域名属于 bootstrap 解析:它发生在代理链路建立之前,没法经由
# 这个尚未连接的代理自己解析。这里仍支持域名,业务网页/API 域名则在
# sidecar ready 后走通用 resolver 和上游代理出口。
UPSTREAM_HOST_IP="$UPSTREAM_SOCKS5_HOST"
if ! [[ "$UPSTREAM_SOCKS5_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  resolved=$(getent ahostsv4 "$UPSTREAM_SOCKS5_HOST" | awk '{print $1; exit}')
  if [ -z "$resolved" ]; then
    log "FATAL: cannot resolve UPSTREAM_SOCKS5_HOST=$UPSTREAM_SOCKS5_HOST"
    exit 1
  fi
  UPSTREAM_HOST_IP="$resolved"
  log "Resolved upstream proxy host: $UPSTREAM_SOCKS5_HOST -> $UPSTREAM_HOST_IP"
fi

cat > /etc/proxychains4.conf <<EOF
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
${PROXYCHAINS_TYPE} ${UPSTREAM_HOST_IP} ${UPSTREAM_SOCKS5_PORT} ${UPSTREAM_USER} ${UPSTREAM_PASS}
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
MITM_SAVE_ARGS=()
if [ "${SAVE_FULL_FLOWS:-0}" = "1" ]; then
  MITM_SAVE_ARGS=(--save-stream-file "$FLOW_FILE")
  log "Full mitm flow capture enabled: $FLOW_FILE"
fi
MITM_IGNORE_ARGS=(--ignore-hosts '^(platform\.claude\.com)$')
if [ "${CAPTURE_FULL_HTTP:-0}" = "1" ]; then
  # 完整抓包 run 要尽量覆盖 OAuth / 平台侧 Claude Code 请求，不能沿用普通 run 的忽略规则。
  MITM_IGNORE_ARGS=()
fi
log "Starting mitmdump (socks5 inbound :8080, upstream via proxychains ${PROXYCHAINS_TYPE} -> ${UPSTREAM_SOCKS5_HOST}:${UPSTREAM_SOCKS5_PORT})"
proxychains4 -q mitmdump \
  --mode socks5 \
  --listen-host 127.0.0.1 --listen-port 8080 \
  "${MITM_IGNORE_ARGS[@]}" \
  "${MITM_SAVE_ARGS[@]}" \
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

# ---------- 4) 创建 tun0 ----------
# 注意:这里只建设备 + 给地址,不动路由表。
# hev-socks5-tunnel 启动时会用 TUNSETIFF 接管 tun0,该过程会触发一次
# link down→up,kernel 把所有指向 tun0 的路由自动清掉。所以 default 路由
# 必须放到 hev 起来之后再加,否则一开机就被吃掉(老代码就是踩这个坑,
# DNS 一直没真走 tun0)。
log "Creating tun0"
ip tuntap add mode tun dev tun0
ip addr add 198.18.0.1/15 dev tun0
ip link set dev tun0 up

# 给上游代理服务器单独留 host route 走 eth0:这条路由不指向 tun0,
# 不会被 hev 清掉,可以提前加。
ETH_GW=$(ip route | awk '$1=="default" {print $3; exit}')
ETH_IF=$(ip route | awk '$1=="default" {print $5; exit}')
if [ -n "$ETH_GW" ] && [ -n "$ETH_IF" ]; then
  ip route add "${UPSTREAM_HOST_IP}/32" via "$ETH_GW" dev "$ETH_IF" || true
  log "Bypass route: ${UPSTREAM_HOST_IP} via ${ETH_GW} dev ${ETH_IF}"
fi

# ---------- 5) hev 配置:tun 流量 → 127.0.0.1:8080 (mitm) ----------
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

# 等 hev 把 tun0 接管完(link down→up 周期完毕),再切默认路由。
# 路由设置是 race-prone:hev 在启动初期可能多次触发 tun0 link 抖动,导致刚加的
# default 瞬间消失再恢复。所以单点检测不可靠,改成"加完路由后连续 3 次确认它
# 还在"才算稳定。最多重试 15 次(每次 0.5s+1.5s 验证 = 2s,总上限 ~30s)。
ok=0
for i in $(seq 1 15); do
  sleep 0.5
  ip link show tun0 2>/dev/null | grep -q "state UP" || continue
  ip route del default 2>/dev/null || true
  ip route add default dev tun0 2>/dev/null || continue
  stable=1
  for j in 1 2 3; do
    sleep 0.5
    ip route | grep -q "^default dev tun0" || { stable=0; break; }
  done
  if [ $stable -eq 1 ]; then
    log "Default route stable via tun0 (after attempt $i)"
    ok=1
    break
  fi
done
if [ $ok -ne 1 ]; then
  log "FATAL: default route via tun0 unstable after 15 attempts"
  ip route
  exit 1
fi

# ---------- 6) unbound: UDP 53 进 → TCP 53 出(走 tun → hev → 上游代理 TCP 隧道) ----------
# 商用代理通常只稳定支持 TCP 隧道,UDP relay 多半不开,所以 hev 的
# udp:'tcp' 不能直接依赖上游 UDP 能力。这里在 sidecar netns 里跑 unbound 做 UDP→TCP DNS 桥:
#   worker → UDP 53 → unbound(127.0.0.1) → TCP 53 → 1.1.1.1 → tun → hev →
#   proxychains → 上游代理 TCP 隧道 → 解析成功
# tcp-upstream:yes 是关键,强制对 forward-addr 走 TCP。
mkdir -p /etc/unbound
cat > /etc/unbound/sidecar.conf <<'EOF'
server:
  verbosity: 0
  interface: 127.0.0.1
  port: 53
  do-udp: yes
  do-tcp: yes
  tcp-upstream: yes
  username: ""
  chroot: ""
  pidfile: ""
  use-syslog: no
  logfile: ""
  hide-identity: yes
  hide-version: yes
  cache-min-ttl: 0
  cache-max-ttl: 60
  access-control: 0.0.0.0/0 allow
forward-zone:
  name: "."
  forward-addr: 1.1.1.1
  forward-addr: 8.8.8.8
EOF
log "Starting unbound (DNS UDP→TCP bridge)"
unbound -d -c /etc/unbound/sidecar.conf >/var/log/unbound.log 2>&1 &
UNBOUND_PID=$!

for i in $(seq 1 20); do
  if ss -ltn 2>/dev/null | grep -q '127.0.0.1:53 '; then break; fi
  sleep 0.25
done

# DNS 指向 unbound;worker 共享 netns 但不共享 mount ns,worker entrypoint 也要
# 自行写一份 /etc/resolv.conf(这里只管 sidecar 自己的解析)。
echo "nameserver 127.0.0.1" > /etc/resolv.conf

# readiness 只验证通用 resolver 链路,不是按业务域名维护白名单。后续 Claude
# 访问任意网页时仍走同一个 127.0.0.1:53 → unbound → tun → 上游代理出口。
DNS_READY_HOST="${DNS_READY_HOST:-example.com}"
for i in $(seq 1 45); do
  # getent 会同时受 glibc/NSS、IPv6 排序和缓存状态影响;ready 阶段只需要证明
  # unbound 能经当前出口拿到通用 A 记录,所以直接查询本地 resolver 更稳。
  if dig @127.0.0.1 "$DNS_READY_HOST" A +time=3 +tries=1 +short 2>/dev/null | grep -q .; then
    touch /tmp/sidecar-ready
    log "Sidecar DNS ready via generic resolver ($DNS_READY_HOST, after ${i}s)"
    break
  fi
  sleep 1
done
if [ ! -f /tmp/sidecar-ready ]; then
  log "FATAL: DNS resolver not ready after 45s for probe host $DNS_READY_HOST"
  tail -80 /var/log/unbound.log 2>/dev/null || true
  exit 1
fi

log "Sidecar up: mitmproxy=$MITM_PID hev=$HEV_PID unbound=$UNBOUND_PID stats=/flows/stats.jsonl"
wait
