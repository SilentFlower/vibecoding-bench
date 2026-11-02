# TLS 版本绑定实施前核对

## 已确认源代码

- 子仓HEAD 71997e7562875dda35b00e2b267c7d6ccd1ed5f7，主仓HEAD 5f125511607f8d68dee91de6cf377d6720b48588；本轮尚未改业务代码。
- src/tlsfp/tlsfp.rs：Native293唯一模板，build_tls_config_with_roots构造真实Provider；REQUEST_CLIENT_CACHE现为HashMap<String,reqwest::Client>，只有代理维度。保留get_request_client/make_request_client兼容入口，新增显式TLS ID入口。
- src/service/version_profile.rs:133 ClaudeCodeProfile当前含identity/access_policy/request/billing/telemetry/endpoints；169选择配置为mode+default_profile；resolve按原始UA精确260/280/293或配置默认，account模式返回None。account_for_request_profile只创建请求副本，不改持久身份。
- GatewayService::reload_access_profile_config在同一写锁读取和替换准入/选择快照；当前count_tokens入口1573及主入口1813只返回request_profile。应同时冻结默认TLS；后续账号选择分别在1688、2174产生request_account。
- forward_request、forward_count_tokens_request分别在2860/3199构造PreparedRequest；401/signature/换号路径都须沿入口快照，不能在最终发送时重新读变化后的默认。
- src/service/runtime_transport.rs：PreparedRequest目前为account_id/environment_id/generation/request_id/deadline_unix_ms/method/target_url/headers/preserve_header_casing；没有TLS字段。send_direct在142调用共享工厂，sender forward先鉴权、解码/校验，再递增active和submitted后调用send_direct。新增枚举ID应在此提交前完成白名单解析。
- src/service/session_hello_probe.rs:303按account代理建client，HTTP画像源于账号副本；telemetry.rs:548在ticker循环外一次建client，需考虑默认变更后的后续tick；oauth.rs包含带version的token验证探针，oauth_flow仅有待授权session代理应沿配置默认。
- v3网关直接向sender传x-v3-request内部元信息；orchestrator/account_runtime.py::transport的version参数只为旧调用兼容，不参与API环境准备。本轮不要把TLS切换接到真实CLI版本或重建账号身份。

## 兼容与测试细节

- 版本可选TLS绑定：293显式绑定；旧版本无正式TLS证据则留空。默认版本也留空时，集中使用内置默认画像的TLS作为兼容末级，不在各调用方硬编码293。以后默认版本有新绑定，所有未绑定版本自动跟随。
- 使用稳定TLS ID而非任意模板JSON；生产注册表仅真实293。测试第二画像仅cfg(test)生成，并实际验证不同wire/缓存，不制造280或303已验证的假象。
- 显式元信息未知ID拒绝，历史缺字段沿原内置默认。普通入口不允许调用方用body或自带内部头决定TLS；sender仍要求内部认证及账号/环境/generation绑定。
- 完整cargo test上轮在默认高并行出现SQLite锁与超时，二次默认和受控4线程均776通过、3项既有PostgreSQL忽略；本轮最终用cargo test -- --test-threads=4，记录新真实结果。
- 私有操作目录.deploy/cc2api-versioned-tls-20261030；初始334项retained精确状态/hash已保存。部署当前批次ci-40979130989-1，已验证模板位于.deploy/cc2api-tls-alignment-20261030；新批次不得复用其release或manifest。

## VM2API和原生293证据边界

- 历史vm2api本地IP实验为17cipher、9sigalg、groups[29,23,24]、单share29:32、ALPNhttp/1.1；无SNI且只采初始握手。
- 当前原版293主请求cipher及sigalg与该局部样本相同，groups增加4588、share为4588:1216后接29:32；域名新连接JA3 1523504b38f0fae0d881d4b6554aac1b。不能直接按IP样本缺SNI的JA3作横比，或把vm2api视为原版293/303。
- 原版293无MITM回环握手已与正式CLI入口证据核对；当前正式cc2api sender也实际复算为同一JA3，详细来源在已交付native TLS任务。

## 已完成核对

普通账号update不更新canonical_env，版本矩阵测试已使用现有update_all_canonical_env_identity专用入口并断言持久结果。sender预提交失败标识实际为before-send，未知TLS测试已按真实契约断言。最终782项完整回归通过、3项既有PostgreSQL忽略。Hello传递冻结TLS且缓存key升级v3，现有探测/并发/故障测试通过。
