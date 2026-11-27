"""使用内置直发候选验证待工具期间的账号 OAuth 轮换。"""

from argparse import ArgumentParser
from hashlib import file_digest
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch

import verify_tui_cold_history as fixture
from verify_tui_core_http_hook import ObservedModel, PROGRAMS
from verify_tui_installed_direct_stock import observe_delivery


def main():
    """在仅回环容器验证实际 CLI 连接、凭据轮换和原回执。@return 脱敏证据。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    assert Path("/opt/flower/tui/fixture-installed-direct").is_file()
    with Path("/cli/2.1.321/node_modules/.bin/claude").open("rb") as binary:
        assert file_digest(binary, "sha256").hexdigest() == PROGRAMS["2.1.321"]
    with patch.object(fixture, "QuietHandler", ObservedModel), TemporaryDirectory() as folder:
        result = fixture.verify(
            Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"), Path(folder),
            oauth_rotation=True, observe_oauth_delivery=observe_delivery, recover_pending=args.restart,
            installed_runtime=True, trace_startup=True, trace_recovery_resend=True,
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
