"""NULL草稿的固定私有操作清单，轻量SSH客户端只装载字符串合同。"""

DRAFT_LOGIN_SHORT_OPERATIONS=(
    'draft-login-grant-create','draft-login-grant-renew','draft-login-grant-get','draft-login-grant-close',
    'draft-login-get','draft-login-observe','draft-login-code-receipt','draft-login-snapshot','draft-login-input','draft-login-files','draft-login-summary',
)
DRAFT_LOGIN_OPERATIONS=DRAFT_LOGIN_SHORT_OPERATIONS+(
    'draft-login-prepare','draft-login-recover-preparation','draft-login-start','draft-login-stop','draft-login-code','draft-login-commit',
    'draft-login-accept','draft-login-discard','draft-login-activate','draft-login-delete','draft-login-delete-preparation',
)
