ARG ACCOUNT_IMAGE=ghcr.io/silentflower/flower2api-account:v3-ci-45743360178-1
FROM ${ACCOUNT_IMAGE}
# 保留发行守卫、受管启动器和账号进程入口，仅安装本次候选源与固定合成模型夹具。
COPY images/account/tui_*.py /opt/flower/tui/
COPY images/account/tui-mod/ /opt/flower/tui/tui-mod/
RUN mv /opt/flower/tui/tui_source.py /opt/flower/tui/tui_source_impl.py
COPY deploy/flower2api/fixtures/native_model_send/source.py /opt/flower/tui/tui_source.py
COPY deploy/flower2api/fixtures/file_activity.py /verify-native/
COPY deploy/flower2api/fixtures/native_model_send/preload.mjs deploy/flower2api/fixtures/native_model_send/scenario.py deploy/flower2api/fixtures/native_model_send/verify.py /verify-native/
COPY deploy/flower2api/fixtures/native_model_send/verify_proxy.py /verify-native/
COPY deploy/flower2api/fixtures/native_model_send/fixture_tunnel.py deploy/flower2api/fixtures/native_model_send/managed_route.py deploy/flower2api/fixtures/native_model_send/verify_managed_proxy.py deploy/flower2api/fixtures/native_model_send/title-usage.mjs services/runtime/src/shared/native-classifier.ts /verify-native/
COPY services/orchestrator/native_capture.py services/orchestrator/runtime_files.py /verify-native/
ENTRYPOINT ["python3", "/verify-native/verify.py"]
CMD ["--gateway", "/verify-native/bin/claude-code-gateway", "--sender", "/verify-native/bin/account-sender"]
