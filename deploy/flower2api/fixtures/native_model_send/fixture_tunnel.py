"""仅隔离验收使用的固定目标账号代理。"""

from select import select
from socket import create_connection
from http.client import HTTPConnection


HOST = "model-probe.invalid"


def _relay(http, remote, opened):
    opened(remote.getsockname()[1])
    http.send_response_only(200)
    http.end_headers()
    peers = {http.connection: remote, remote: http.connection}
    while readable := select(list(peers), [], [], 30)[0]:
        for peer in readable:
            chunk = peer.recv(65536)
            if not chunk:
                return
            peers[peer].sendall(chunk)


def connect_model(http, model_port, opened):
    """接通唯一的合成模型。@param http 测试连接。@param model_port 夹具创建的回环模型端口。
    @param opened 记录已连接对端的回调。@return 无。
    """
    if http.path != HOST + ":443":
        return http.send_error(403)
    with create_connection(("127.0.0.1", model_port), timeout=10) as remote:
        _relay(http, remote, opened)


def connect_account_fixture(http, proxy_port, opened):
    """会话经指定的本机测试代理接通唯一的模型。@param http 会话连接。
    @param proxy_port 已核对的合成账号代理端口。@param opened 记录两跳关联。@return 无。
    """
    if http.path != HOST + ":443":
        return http.send_error(403)
    connection = HTTPConnection("127.0.0.1", proxy_port, timeout=10)
    try:
        connection.set_tunnel(HOST, 443)
        connection.connect()
        _relay(http, connection.sock, opened)
    finally:
        connection.close()
