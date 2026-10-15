# Brief — v3 GHCR 发布与美国服务器隔离部署

## Goal

- 将同批 control/account 两镜像发布到 GHCR，并在美国服务器部署可核对版本的独立 v3。

## Scope

- 补齐两镜像发布、联合清单和同批镜像包。
- 增加账号 swap 配置及对应的资源预检。
- 在 us.flower-cli.com 部署并验证独立管理入口。

## Non-Goals

- 不接管旧账号、旧流量或旧数据库，不启动真实账号养号和模型调用。
- 不改 cc2api 请求协议，不合并 main，不实施额度阈值或遥测修复。
- 不自动改变 GHCR 包可见性或在服务器保存新增 PAT；arm64 与真实 CLI 峰值另行验收。

## Technical Overview

- 同一 Action 构建并发布两个镜像，使用专用包名和相同唯一批次标签；联合清单分别保存本地镜像配置 ID 与仓库 digest。
- 远程优先按 digest 拉取；首次私有包不可匿名拉取时，使用同批镜像包并校验 SHA256。
- 每账号 1536 MiB RAM＋2048 MiB swap，Docker 总额度 3584 MiB，活跃账号上限 1；预检分别核对 RAM 和 swap，账号预算随固定环境保存。

## Context & Decisions

- 用户已确认本次低内存预算；服务器快照约 2.7 GiB 可用 RAM、6.3 GiB 空闲 swap，18080 空闲。默认 4 GiB、swap 关闭的行为仍兼容。
- 新入口 http://us.flower-cli.com:18080；安装目录 /opt/vibebench-v3-us，数据目录 /srv/vibebench-v3-us，采用独立管理密码。
- 初次启动两个管理服务和空数据库，账号容器随新增账号创建；旧 8080、5674 服务保持原样。

## Risks

- 真实 CLI 的内存峰值和频繁交换时的延迟尚未验证。
- 部署前资源余量可能变化；实时预检不通过则停止，保留旧服务。
- GHCR 首次包可见性待发布后核对，同批镜像包提供交付路径。

## Acceptance

- Action 发布两个同批镜像，清单及镜像包可核验；失败不产生完整交付清单。
- 实际 Docker RAM/swap 上限与配置一致，历史环境保持兼容。
- 新版管理服务健康，登录、环境列表、HTTP/SSE/WS 鉴权与退出通过。
- 旧 bench/cc2api 的容器、启动时间和服务状态不受部署影响，交付精确版本与回退方式。

## Next Step

- 启动任务，先实现共享资源解析与账号 swap 配置。
