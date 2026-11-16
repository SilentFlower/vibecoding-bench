# 代理目录与账号选线

## 1. Scope / Trigger

适用于Rust代理目录、出口观测、跨服务引用投影、账号选择代理以及代理目录版本2与关联同步版本3迁移。

## 2. Signatures

- `GET /admin/proxies?page=1&page_size=20&q=&usage=true`：每页1～100条，搜索最长256字节。`usage=false`供选线和批量检测读取，省略运行时引用聚合。
- `POST /admin/proxies`、`PUT /admin/proxies/:id`：`name/protocol/host/port/username?/password?/expires_at/revision?`；更新必须匹配revision。
- `POST /admin/proxies/identify`、`POST /admin/proxies/import`：`{text}`，导入1～200行，全部验证后在同一事务写入。
- `POST /admin/proxies/:id/probe`；`DELETE /admin/proxies/:id`带`{revision}`。
- 内部 `tlsfp::make_request_client_builder() -> reqwest::ClientBuilder` 提供当前默认指纹、公有信任根和禁用环境代理的基础配置；探测在其上设置独立请求边界。
- 账号创建/增量更新兼容`proxy_url`，增加虚拟`proxy_id/proxy_revision`。两种选择不能同时提交；更新`proxy_id:null`为直连。

## 3. Contracts

- 账号权威字段仍是`Account.proxy_url`。目录ID在服务端重新解析为连接，并继续经过账号原配置维护门禁。目录写入与网关账号选线共用`ProxyService.mutations`；版本检查防止迟到编辑覆盖。
- 列表公开名称、类型、主机、端口、无认证地址、认证是否存在、到期、观测与使用者。私有认证、内部摘要及原始数据库错误不得公开。编辑未提交认证字段表示保留，显式空字符串清除。
- HTTP/SOCKS5/SOCKS5H主机先经HTTP网络主机规则统一大小写、IDNA及IPv6。内部引用摘要为UTF-8紧凑JSON数组`[protocol,host,port,username,password]`的SHA256；Python使用相同合同。
- 引用涵盖网关账号、未绑定任务账号和登录草稿。已绑定任务由网关计数；停用账号仍属于引用。未知引用不冒充零使用，连接改写及删除失败关闭。使用中连接参数可直接编辑，目录CAS与固定关联目标在同一事务登记后台同步；名称与到期可独立编辑。同步期间进一步的连接变更等待当前批次收口。
- 到期仅用于维护提醒。列表搜索只匹配公开字段，并在分页前使用同一过滤条件统计总数。账号页的目录匹配批量读取，引用聚合不逐条创建排队器。
- 出口探测固定`https://ipwho.is/`，不跟随重定向；并发4、连接超时5秒、请求8秒、整体10秒、响应最多64KiB。成功仅保留IP/国家地区城市/耗时与时间戳。失败保留上次成功观测并标记失败。连接或元数据revision变化后丢弃迟到探测。
- 探测必须复用带指纹的TLS构建器，并显式挂载所选私有代理；证书与主机名校验继续开启。普通`reqwest::Client::builder()`缺少craftls必需的fingerprint，会在HTTPS握手时panic并使管理连接断开。构建器复用不改变转发客户端的长流超时策略。
- SQLite追加`gateway.proxies.2`，基线1保持冻结。目录DDL与台账在同一事务，提交前检查主键/唯一约束。PostgreSQL使用相同目录DDL初始化；SQLite校验不可在PostgreSQL运行。调整未发布版本2定义后同步登记checksum。

## 4. Error Matrix

非法参数/重复连接/版本冲突/同步中再次改连接或删除已引用线路返回受控400；引用不可核对返回503；并发检测容量满返回429；不存在返回404。探测网络失败以`status=failed`表达，同时保留旧观测。

代理CONNECT后的TLS断连也走`status=failed`与历史观测保留路径；不得以panic断开管理响应。

## 5. Good / Bad Examples

正确：账号保存`{proxy_id:"UUID",proxy_revision:"打开时版本"}`，由服务端解析账密。错误：从公开列表恢复密码，或代理页直接改多个账号绑定。正确：修改到期采用CAS且保留刚完成的最新观测。错误：用打开表单时的旧观测覆盖数据库。

正确：探测使用`make_request_client_builder().proxy(Proxy::all(private_url)?)`并设置5/8秒超时、禁止重定向。错误：直接用普通reqwest构建器发送HTTPS，或在代理失败后回退直连。

## 6. Verification

`cargo test --locked --manifest-path services/gateway/Cargo.toml`；聚焦`--lib proxy`及`--lib store::`；Python `test_proxy_references`；浏览器`deploy/flower2api/verify_proxy_design.py`。覆盖分页、字面搜索、导入回滚、凭据保护、CAS、迟到观测、账号草稿及窄屏。

`probe_sends_tls_clienthello_and_records_connection_failure`使用本地认证HTTP代理接收真实CONNECT与TLS ClientHello，再主动断连；断言检测正常返回failed、更新检测时间且保留历史IP和观测时间。测试只使用合成账密，并验证实际握手路径，避免仅测JSON解码而遗漏craftls初始化。

## 授权目录选择补充

OAuth及Setup Token的generate接口增加proxy_id/proxy_revision；保留proxy_url兼容，两个连接来源同时出现返回400。handler解析当前目录并校验revision，私有URL冻结到原内存授权会话。未过期会话计入目录使用者kind=authorization，只读展示；请求不返回代理认证。交换阶段与目录破坏性更新共用配置锁，防止会话take之后仍使用连接时目录变更。浏览器授权结果填写账号时沿用生成链接时的选择。

## 任务账号授权目录选择

`POST /runtime/api/accounts/login/start` 可携带 `proxy_id/proxy_revision`。桥接先校验原会话和来源，再持有 `ProxyService.mutations`，将目录记录解析为运行时原有的 `upstream_*` 字段，保持锁直到启动回执返回。显式 `proxy_id:null` 表示直连，目录ID与手动连接字段混用返回400，revision不符要求重新选择。已有手动请求保持兼容。

所选私有连接不返回浏览器。下游错误返回受控说明，成功响应仅允许原 `_login_response` 的会话公开字段，避免下游校验错误回显目录账密。已绑定任务重授权继续由编排服务采用权威关联配置。

目录列表顶层 `counts` 独立于搜索和分页：`all/available/used`。引用不可核对时 `used:null`；选择组件的 `usage=false` 跳过引用和汇总查询。

## 使用中连接的持久同步

- `PUT /admin/proxies/:id` 的 `sync_pending` 表示目录已保存、关联副本尚待收口。列表在同步期间合并旧/新连接使用者；账号列表继续匹配同一目录ID。旧连接在待同步期间禁止被另一目录复用。
- SQLite版本3 `gateway.proxy-sync.3` 保存私有源/目标及kind/id目标清单；版本1/2摘要保持。后台启动恢复，单工作协程逐个目标持有目录锁；空队列退出与新任务唤醒在同一锁下收口。
- 网关目标强制取得`config_permit(...,true)`门禁；无运行时部署只验证网关队列，有运行时继续quiesce。仅`proxy_url`按旧值CAS更新，保留凭据、限额和状态，沿原调度失效及原生准备通知。
- 部署门禁在后台目标执行时登记活动。编排端`POST /internal/v3/proxy-sync`沿内部证明和UPDATE_GATE，按owner→profile→environment非阻塞取锁，活动登录/CLI/API保持待重试；空闲停止并移除旧实例，保留持久资料后更新私有代理。已提交草稿转task，已绑定task转gateway。
- 回执丢失按当前连接幂等确认；用户已切至第三条连接时保留当前选择。同步错误不返回私有连接或数据库原始错误。删除继续使用完整引用保护。
- 验证：`used_proxy_edit_queues_until_idle_and_synchronizes`覆盖真实路由/SQLite/工作协程、忙碌延期及空闲回读；`proxy_sync`存储与`test_proxy_sync.py`覆盖恢复、CAS单列、锁/停止失败、草稿转换及凭据保护。

## Scenario: 任务账号选择与超时事务保护

### 1. Scope / Trigger

修改任务选线、运行时代理桥、内部提交或目录引用保护时适用。浏览器只提交目录身份，私有连接由Rust解析。

### 2. Signatures

- `GET /runtime/api/accounts/:id/proxy-selection`返回`account_id/name/gateway_account_id/selection_revision/current`。
- `PUT`同一路径仅接受`selection_revision:string`、`proxy_id:string|null`、可选`proxy_revision:string`；直连不接受线路版本，额外字段拒绝。
- 内部运行时PUT接收`selection_revision/connection/operation_id`三个严格字符串。operation_id为32位hex票据，不向浏览器返回。
- 内部`POST /admin/runtime/task-proxy-operations/:operation/claim`接收`account_id/gateway_account_id/selection_revision/connection`，返回`claimed:true`。
- 内部`POST /admin/runtime/accounts/:id/proxy-selection`接收`operation_id/expected_connection/connection`，返回`ok:true`；两条内部路由均要求原管理员认证及`x-v3-service-token`。

### 3. Contracts

- public current区分directory/custom/direct/unknown，仅含目录名称、ID、revision、脱敏地址、检测及到期。列表一次批量匹配私有连接和待同步旧别名；绑定任务取网关权威，读取异常保持unknown。新增投影与选择接口不公开私有认证和源摘要，原任务列表字段保持兼容。
- selection_revision由编排使用V3_INTERNAL_TOKEN的HMAC-SHA256计算，绑定任务、当前绑定与实际连接；64位hex仅作版本校验，原会话/来源保护继续生效。响应读取最多4MiB，内部网络等待45秒；错误正文使用固定公开说明。
- `ProxyService.mutations`为共享Arc互斥锁。解析目录及版本后创建弱登记票据，票据强引用持有目录许可。任务身份、版本及目标逐项匹配，领取仅一次；绑定记录冻结到领取时刻。原等待退出后，已失效票据无法再次领取。
- 编排先登记活动再领取，活动期间引用complete=false；读取跨越活动代次也为false。未决目标尚未进入账号记录时，目录删除/连接修改仍失败关闭。名称与到期维持原独立编辑语义。
- 绑定回调持有已领取票据的强引用，并核对绑定与目标，目录许可覆盖最终CAS；外层超时或断连不会撤销已进入回调的许可。其后复用config_permit(...,true)、凭据门禁及代理单字段CAS，保持限额、状态、凭据和原生准备失效通知。
- 原Gateway进程重启使票据失效；独立任务仍由编排活动保护。编排重启会终止本地执行，已进入网关的回调继续持有自身许可。与现有单进程编排维护锁边界一致；扩多进程前须重新设计共享活动与票据所有权。

### 4. Validation & Error Matrix

- 非法身份/目录缺失：404；载荷或目录版本不符：受控400。
- 任务原版本/绑定变化、忙碌、停用：409；服务未知或超时：503，界面先回读结果再决定重试。
- 未领取、重复领取、过期或目标/绑定不符的内部票据：受控400；公开桥不返回内部错误正文。
- 未决操作/跨代次引用读取：complete=false，目录删改503；实际事务完成后重新读取正常引用。

### 5. Scenarios and Examples

正常：`{selection_revision:"64位hex",proxy_id:"目录ID",proxy_revision:"原版本"}`由桥解析并受控提交。边界：直连使用proxy_id:null。错误：HTTP超时后仅释放锁并允许目录删除；正确处理是已领取操作持续登记引用保护，未领取迟到请求被票据拒绝。单纯增加HTTP超时不能替代事务保护。

### 6. Tests Required

Rust票据测试覆盖过期、重复领取、身份/绑定核对、回调强引用及目录锁释放；`test_task_proxy.py`覆盖实际入口、活动及引用代次。`verify_task_proxy_api.py`用真实Rust HTTP、Python产品保存和两份SQLite验证关联/独立/直连、45秒超时删改503、提交后恢复及过期请求拒绝。全量`cargo test --locked --manifest-path services/gateway/Cargo.toml`和fmt必须通过。
