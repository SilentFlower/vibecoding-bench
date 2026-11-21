# AGY运行环境实现与验证进度

## 已完成

- 已取得完整Brief人工批准并激活任务，implement route=inline。
- 原型Python/C源码及文本资源导入services/orchestrator/agy_runtime，正式OAuth启动移除研究API Key和测试CA依赖。
- AT-only工作文档与私有文件读取、模型目录映射、temperature/topP原生默认兼容、Part/签名/usage投影及工具历史/ID归属校验已实现。
- 校验从assert改为明确运行时检查，优化模式保留归属门禁。默认协议输出采用匿名有界暂存，普通业务归档在作业结束回收；显式采集继续私有保存。
- 观察器与回收库从受管理源码构建。固定模型常量改为进程启动时从已核验目录冻结；StartCascade与plannerConfig.planModel保持同一执行ID。

## 当前证据

| 验证 | 结果 |
| --- | --- |
| 最新Python定向回归 | AGY核心、监督器、环境、原AccountRuntime、迁移、数据定义、宿主升级及源码布局共181项通过；后续核心20项通过，.trellis/.runtime/agy-runtime-repair-final-python.log和agy-runtime-repair-python.log |
| Rust回归 | 完整套件965项通过、13项忽略，后续修改的四组定向11项通过；.trellis/.runtime/agy-runtime-rust-all-tests.log和agy-runtime-focused-rust-tests.log |
| 部署回归 | 223项通过，.trellis/.runtime/agy-runtime-deploy-tests.log |
| C构建 | gcc -Wall -Wextra -Werror通过，.trellis/.runtime/agy-runtime-native-build.log |
| 固定原版断网启动与故障收口 | UID1001、cap-drop ALL、no-new-privileges、network=none、合成AT；两代准备、完整265700040字节封存映像仅解码一次，正常关闭和杀监督器后进程终止通过。模型提交0，.trellis/.runtime/agy-runtime-native-normal.log和agy-runtime-native-crash.log |
| 真实HTTP与SQLite | 原生发送边界采用替身，12次合成提交；Gemini、工具原许可接续、pending旧工具收口、认证恢复、首帧后禁重放和断连取消通过，.trellis/.runtime/agy-runtime-http-sqlite.log |
| 固定原版本地TLS业务闭环 | 真实网关、SQLite、account-sender、监督器、原版及MCP，9次本地合成原生生成通过；覆盖非流式/SSE、AT两代、并发1工具续轮、重复拒绝、64重复帧与SIGURG、截断/容量错误、断连取消及许可释放。768MiB限制下整体峰值465899520字节；真实外部生成0，.trellis/.runtime/agy-runtime-native-loopback.log |
| 修复回归 | 共享传输10项及四组集成11项通过，.trellis/.runtime/agy-runtime-repair-rust-transport.log和agy-runtime-repair-final-rust.log；资源镜像按修复后源码重新构建，agy-runtime-repair-docker.log |
| 浏览器 | 真实Vue与合成后台，1440/720/390px、草稿焦点、控件边界、离页清理通过，.trellis/.runtime/agy-runtime-ui-tests.log |
| 构建与数据定义 | Vue构建、agy-runtime-build资源阶段镜像、bench 2项与gateway 5项数据定义校验通过；日志前缀.trellis/.runtime/agy-runtime- |

Orchestrator全量1362项有1项错误、5项跳过，错误为python-dateutil项目种子摘要不一致。git archive HEAD隔离核对得到同一摘要差异，证据为.trellis/.runtime/agy-runtime-baseline-project-content.json。该项属于已有项目内容基线异常。最新任务相关定向171项通过。

原生探针必须采用只读封存映像。镜像overlay直接执行路径的/proc映射文件身份存在不一致，原型的文件路径基址识别失败；共享memfd路径按完整SHA、大小、四封存及同背板核验通过。私有原版文件作为直接挂载输入也遇到执行权限限制；探针最终使用已核验测试镜像内执行体，原私有原件保留原状。

## 实施状态

1. 账号内监督进程、共享映像池及私有信封已接线，工具结果先原worker收尾，再按当前代次开始下一轮。
2. 现有account-sender AGY分支、Gemini路由、权限/调度/限流/取消链路已接线。
3. AccountService AT快照、AccountRuntime平台环境、追加迁移、资源与环境UI、镜像构建接线已实现。
4. 用户选择修复全部后，cgroup v1预算兼容已修复。补齐固定原版TLS闭环时还修复共享准入的AGY动作路径、OAuth观察器、截断流终态及正式镜像共享Python模块路径。原v1失败复现保留在.trellis/.runtime/agy-runtime-audit-cgroup-v1.json，修复后有限/无限/未知及不匹配回归通过。

本地TLS入口为verify_agy_native_loopback.py --image flower2api-agy-auth:task-smoke --loader-root /lib/x86_64-linux-gnu。loader-root为本轮调试Rust产物提供显式glibc输入；普通兼容制品可省略。一次性CA只挂入断网验证容器的系统信任根，正式OAuth配置保持正常证书校验。runtime_files挂载位置与正式镜像同为/usr/local/bin，worker冻结模块路径保留该目录。

OAuth观察器保留完整源SHA、映像及四槽指令校验；原型API Key的SDK观察位置改为固定codeassist Scanner逻辑块和channelModelResponseStream接收位置。Scanner信封解包后输出Gemini源JSON，EOF独立保留错误未知标记；成功须同时核对源终态与真实控制RPC，截断文本返回失败。

真实Google身份、模型接受性与跨实际到期继续保留外部验证，本任务真实模型预算0。
