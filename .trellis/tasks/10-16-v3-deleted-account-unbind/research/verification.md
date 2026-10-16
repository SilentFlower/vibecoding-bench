# 验证证据

## 缺陷与基线

- 2026-10-16 只读线上查询：bench `10-15` id=3 绑定 cc2api id=2，gateway accounts 为空；环境均 stopped，近四次 DELETE cc2api-binding 返回 409。没有为诊断改生产数据或发送上游请求。
- 修复前聚焦测试产生实际 HTTPError 404 → ValueError → HTTPException 409 链，证明断点位于原绑定门禁查询。

## 已通过

- `/tmp/v3-unbind-venv/bin/python -m unittest discover -s orchestrator -p 'test_*.py'`：277 项，32.095 秒，exit 0；`/tmp/v3-unbind-python-final.log`。
- 新回归 11 项：删除后解绑与重复调用、原本地账号删除、GET/prepare 间删除、HTTP/网络拒绝、坏列表/缺页/错误路由、后续页仍有原账号、本地作业、发送器占用/未知、改绑严格保护、正常门禁、HOME/profile/设备保留。
- Python AST/py_compile、`node --check webui/app.js`、`git diff --check` 通过。未修改 Rust、Vue、schema 或运行依赖。

## 集成准备

- 完整场景已纳入用户批准的 PRD/Brief：隔离正式远端删除→调度器重启→页面解绑→HTTP/双 SQLite/持久文件核对→重复解绑。
- 本次随机部署、空数据库与合成 OAuth/CLI，只使用本地代理；不访问真实 OAuth、usage 或模型。结束按精确随机标签清理；旧哨兵文件/进程保护沿用现有堆栈验收。
- Chrome CDP、HTTP requests、SQLite 和 Docker 能力齐全。复用现有 URL、会话、表名与隔离方式，没有新环境常量待写 playbook。
- Docker 默认网络池已有其它项目网络；临时验收包装只选择不重叠的 10.231.200–249/24 子网，其余标准管理预检和断言保持，不 prune 或停止其它项目。
- 联合构建 A 与最终 B 均 exit 0；B 纳入最后显式导入样式调整。清单 `/tmp/v3-unbind-final-manifest.json`，日志 `/tmp/v3-unbind-final-build.log`，批次 `unbind-20261016-b`。
- 当前输入重算冻结 SHA256=`bacb251e9fb4eae1668c757148625fbc637d5601e1574bdabe40f863b687953d`，与最终 B 清单一致；不部署 A。

## 集成结果

- 实际命令：`/tmp/v3-unbind-venv/bin/python -u /tmp/v3-unbind-stack-isolated.py --manifest /tmp/v3-unbind-final-manifest.json --browser --deleted-binding`，exit 0，日志 `/tmp/v3-unbind-stack.log`；包装只为本次 Compose 指定未占用 `10.231.200.0/24`，标准 preflight、启动、停止、备份与所有断言不变。
- 正式 cc2api DELETE 删除合成账号，独立 SQLite 读者确认远端为 0、本地仍指向原 ID；重启真实 orchestrator 后，Chrome 点击原解绑按钮得到 HTTP 200，SQLite 绑定为 null、养号 off、next=null，页面恢复创建/关联按钮。
- 第二次 API 解绑仍 200；原环境 ID、固化画像、四份 HOME/profile 身份凭据内容保持；合成代理没有 usage 调用记录。
- 同次统一会话、HTTP/SSE/WS、真实退出与旧 Cookie 拒绝、停止保留数据、离线导入幂等、SQLite 停机快照和旧哨兵 StartedAt/hash 均通过。
- 本次合成账号/环境记录、容器、网络和临时数据目录均收口；没有生产数据变更或真实 OAuth/模型请求。原有 55 项 dirty 的未跟踪文件 SHA256 与 tracked diff SHA256 均匹配建任务基线，子仓 clean。

## 上线后验证

- 推送发布并部署后，使用正式解绑 API 解决 id=3 的已确认悬空绑定，检查养号关闭、HOME/设备/凭据与停止状态。当前未执行，不计通过。
