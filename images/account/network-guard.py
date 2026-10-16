#!/usr/bin/env python3
"""只在账号网络命名空间配置默认拒绝，宿主防火墙不受影响。"""
import ipaddress
import json
import os
import subprocess


def apply_rules(proxy_ip: str, proxy_port: int, managers: list[str]) -> None:
    """原子替换账号过滤规则，只允许代理、TUN 和受鉴权的管理入站。

    :param proxy_ip: 已由管理端解析的 IPv4 代理地址。
    :param proxy_port: 代理 TCP 端口。
    :param managers: 本部署管理端及桥网关 IPv4。
    :return: None；安装规则失败时不可发布网络就绪。
    """
    address = ipaddress.IPv4Address(proxy_ip)
    if not 1 <= proxy_port <= 65535 or not managers:
        raise ValueError('账号网络例外配置无效')
    manager_addresses = sorted({str(ipaddress.IPv4Address(value)) for value in managers})
    rules = ['*filter', ':INPUT DROP [0:0]', ':FORWARD DROP [0:0]', ':OUTPUT DROP [0:0]',
        '-A OUTPUT -d 127.0.0.11 -j DROP',
        '-A INPUT -i lo -j ACCEPT', '-A OUTPUT -o lo -j ACCEPT',
        '-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
        '-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
        f'-A OUTPUT -p tcp -d {address} --dport {proxy_port} -j ACCEPT']
    # 即使本地测试代理能访问部署桥网，也不能把内部目标通过 TUN 绕回其他账号。
    for private in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '224.0.0.0/4'):
        rules.append(f'-A OUTPUT -d {private} -j DROP')
    rules.append('-A OUTPUT -o tun0 -j ACCEPT')
    for manager in manager_addresses:
        rules.append(f'-A INPUT -p tcp -s {manager} --dport 8091 -j ACCEPT')
    rules.append('COMMIT')
    subprocess.run(['iptables-restore', '--wait', '5'], input='\n'.join(rules) + '\n', text=True, check=True)
    subprocess.run(['ip6tables-restore', '--wait', '5'], input=(
        '*filter\n:INPUT DROP [0:0]\n:FORWARD DROP [0:0]\n:OUTPUT DROP [0:0]\nCOMMIT\n'), text=True, check=True)


def main() -> None:
    """读取管理端发布的非业务配置并安装过滤规则。

    :return: None。
    """
    apply_rules(os.environ['UPSTREAM_SOCKS5_HOST'], int(os.environ['UPSTREAM_SOCKS5_PORT']),
        json.loads(os.environ['V3_MANAGEMENT_ADDRESSES']))


if __name__ == '__main__':
    main()
