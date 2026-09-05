# cc2api 标题及端点请求头修复部署

用户已于 2026-09-05 授权推送和部署。修复已推送，CI 成功，生产于北京时间 2026-09-05 14:15:57 完成更新，健康与数据检查通过。

## 交付范围

- 标题 fallback beta 白名单及后台端点 UA/beta 修复。
- 无 DB/schema/settings 变化；worker JWT 和 API 状态/缓存方案未实现。
- 不重新部署 bench，不发送主动模型探测请求。

## 已有验证

格式检查、169 项改写器回归、567 项全量测试及 21 项 CCH 定向测试通过。

## 部署证据

- cc2api：`51b130302394d713fbf0e45af89b0764c9af20f7`；父仓 gitlink/规范：`1e70e79`，均已推送。
- CI Docker：[33949029656](https://github.com/SilentFlower/cc2api/actions/runs/33949029656)，成功。
- 目标 tag：`ghcr.io/silentflower/claude-code-gateway:sha-51b1303`，部署前必须核对 revision。
- 旧镜像 revision：`7aecda39da8719f6d61af07274038bb6eb1389e5`；保留 tag：`rollback-header-51b1303-from-7aecda3`。
- 备份目录：`/root/claude-code-gateway/backups/deploy-20260905T061125Z-header-compat-51b1303`，配置与 SQLite 数据库备份已完成，完整性 `ok`。
- DB 备份 SHA256：`5ee29a11ab217969681022799eb81e249d8ba2415505726a0f4c5959b3c28922`。
- Compose 只修改有效的 image 配置行并固定到 digest：`sha256:dd3cc8e25c886a171e132afb4330d671b4cba4943564bc15486e3cc221b06865`；其余解析后配置保持一致。
- 新容器 `25cf570fa56e`，镜像 revision 为 `51b130302394d713fbf0e45af89b0764c9af20f7`；状态 running、重启次数 0。
- 生产本地 `/`、`/api/hello` 与外部入口均返回 HTTP 200。
- 在线 DB 完整性 `ok`；4 个账号仍为 2.1.260，部署前后 settings、账号能力配置摘要一致；两个环境文件及原数据卷保持一致。
- 启动检查窗口 panic、migration failure、ERROR 计数均为 0；bench orchestrator 容器未变。
- 没有发送真实模型测试请求；线上请求头行为复用本地协议 fixture 与全量测试证据，不宣称已完成线上逐请求验收。

## 部署过程说明

- 首次部署前的文本匹配校验因 Compose 注释包含同一镜像行而停止，当时尚未修改配置或重建服务。改为精确匹配有效行后，解析校验确认只有 image 变化，再执行部署。
- Compose 提示既有 volume 并非由其创建；本次继续使用同一个 `docker_claude-code-gateway-data`，部署后已核验数据完整性和配置一致性。

## 回滚材料

已保留旧镜像 tag、原 Compose、两个环境文件和 SQLite API 生成的数据库备份。若需回退本次请求头改动，可将当前服务镜像改回保留的旧镜像后 recreate；本次没有数据库结构迁移，不应默认恢复整库以覆盖部署后的业务数据。未执行生产回滚。
