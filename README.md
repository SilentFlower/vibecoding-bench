<div align="center">

<img src="apps/web/public/favicon.svg" alt="flower2api 标志" width="88" height="88" />

# flower2api

**面向 Claude Code 的自托管 API 网关、账号环境与工程任务平台**

[![联合构建](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-build.yml/badge.svg?branch=flower2api)](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-build.yml)

[快速开始](#快速开始) · [客户端接入](#客户端接入) · [系统更新](#系统更新) · [文档](#文档) · [开发](#开发) · [反馈](https://github.com/SilentFlower/vibecoding-bench/issues)

</div>

把账号接入、API 转发、运行环境和工程执行放在同一个后台管理。你可以为客户端提供统一的 Claude API 入口，也可以让 Claude Code 在持久账号环境中执行工程任务，并查看请求、进程和任务的实际状态。

## 能做什么

| 能力 | 使用方式 |
| --- | --- |
| 多账号 API 网关 | 管理账号池和访问令牌，调度请求，查看用量与配额 |
| 持久账号环境 | 为每个账号保留独立 HOME、代理、CLI 版本和工作目录 |
| 请求诊断 | 按请求 ID 查看处理链路、响应结果、分段耗时与按需采集内容 |
| 原生请求后端 | 按账号选择请求后端，查看热进程就绪情况，管理内核准备、激活与回滚 |
| 工程任务编排 | 通过 Pi 驱动 Claude Code，执行工程迭代、功能开发、缺陷修复和验收 |
| 后台系统更新 | 安装经过双库兼容演练的签名发行，更新前保存快照，支持原地升级与受控回退 |

工程目标库提供 **100 个项目、600 个功能或缺陷修复目标**，可用于工程执行与评估。项目和目标说明见[工程库](resources/project-library/README.md)，题库见[题库说明](resources/topics.md)。

## 快速开始

平台通过同批次的 **control / account 两类镜像**部署，管理服务和账号角色在独立 Docker 网络中协作。配置示例默认监听 `127.0.0.1:18080`。

### 部署平台

1. 从[发行页](https://github.com/SilentFlower/vibecoding-bench/releases)获取同一批次的发布清单与镜像制品。
2. 按[部署指南](deploy/flower2api/README.md)准备配置，填写独立数据目录、镜像引用、发布清单及管理密码。
3. 使用仓库中的统一入口检查并启动。下面的路径替换为已填写完成的部署配置：

```bash
scripts/flower2api-stack check --env /absolute/path/flower2api.env
scripts/flower2api-stack up --env /absolute/path/flower2api.env
scripts/flower2api-stack status --env /absolute/path/flower2api.env
```

宿主要求、内存与 swap 预算、代理配置和备份方式见[部署指南](deploy/flower2api/README.md)。远程访问按部署环境配置 HTTPS 反向代理。

### 登录和配置

打开部署地址，使用配置中的 `V3_ADMIN_PASSWORD` 登录管理后台。

1. 在「账号」中添加账号并完成授权，配置对应代理与请求后端。
2. 在「环境」中查看账号状态、资源与原生内核，按需配置运行时段和内容采集。
3. 在「令牌」中创建供客户端使用的 API 令牌。
4. 接入客户端后，在「请求记录」查看实际请求；工程执行通过「任务」入口管理。

## 客户端接入

flower2api 提供 Anthropic Messages 请求入口。客户端使用管理后台「令牌」中创建的 API 令牌。

### Claude Code

在准备运行 Claude Code 的终端中设置网关地址与令牌：

```bash
unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN
export ANTHROPIC_BASE_URL="http://127.0.0.1:18080"
export ANTHROPIC_AUTH_TOKEN="<在令牌页面创建的 API 令牌>"
claude
```

远程使用时，将地址替换为部署实例的 HTTPS 地址。

### 其他 API 客户端

| 配置项 | 值 |
| --- | --- |
| Base URL | 部署实例地址，例如 `http://127.0.0.1:18080` |
| 请求路径 | `POST /v1/messages` |
| 鉴权 | `x-api-key: <API 令牌>` 或 `Authorization: Bearer <API 令牌>` |

Base URL 是否包含 `/v1` 取决于客户端自动追加的路径，最终请求地址应为 `<部署实例地址>/v1/messages`。

## 系统更新

已接入更新器的实例，在后台「系统更新」检查可用发行并安装。更新流程包含签名与制品校验、在途工作排空、数据库快照和切换后的状态核对。

现有 v3 实例沿原部署持续升级，保留数据根、账号环境和持久身份。首次接入更新器及旧底座补齐能力，按[系统更新 SOP](deploy/flower2api/SYSTEM-UPDATES.md)执行。

构建、正式发行和实例安装分别操作：普通 push / PR 运行[联合构建验证](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-build.yml)；正式发行通过[手动发布](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-release.yml)选择目标分支并勾选 `publish`；管理员在实例后台安装已发布版本。

## 文档

| 你要做什么 | 文档 |
| --- | --- |
| 部署、配置资源与备份 | [部署指南](deploy/flower2api/README.md) |
| 升级现有实例、接入更新器与回退 | [系统更新 SOP](deploy/flower2api/SYSTEM-UPDATES.md) |
| 了解网关、账号池与管理服务 | [网关说明](services/gateway/README.md) |
| 了解账号环境和工程调度 | [编排服务说明](services/orchestrator/README.md) |
| 联调原生运行时与日志工具 | [运行时说明](services/runtime/README.md) |
| 使用工程目标库 | [工程库](resources/project-library/README.md) · [题库](resources/topics.md) |
| 查找源码目录与验证入口 | [单仓说明](docs/migrations/flower2api-layout.md) |

## 开发

当前统一源码位于 `flower2api` 分支：

| 目录 | 内容 |
| --- | --- |
| [apps/web](apps/web) | Vue 管理后台 |
| [apps/legacy-web](apps/legacy-web) | 工程、任务和账号静态页面 |
| [services/gateway](services/gateway) | Rust 网关与账号池 |
| [services/orchestrator](services/orchestrator) | Python 编排服务 |
| [services/runtime](services/runtime) | 原生内核适配与诊断工具 |
| [deploy/flower2api](deploy/flower2api) | 联合构建、部署、备份与更新 |

从仓库根构建管理后台：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run build
```

网关、编排与运行时各自的依赖和验证命令见对应模块 README。仓库级模块入口与命令汇总见[开发导航](docs/migrations/flower2api-layout.md#模块与命令)。

## 反馈与来源

问题反馈和功能建议请提交到 [GitHub Issues](https://github.com/SilentFlower/vibecoding-bench/issues)。反馈时可附部署版本、复现步骤和脱敏后的错误信息。

flower2api 整合自 cc2api、vibecoding-bench 和 cc-runtime-bridge。组件来源、固定提交与执行制品见[来源记录](docs/migrations/flower2api-sources.json)。旧版使用说明保留在[历史 README](README.legacy.md)，网关导入时的介绍及贡献者信息见[上游说明](services/gateway/README.upstream.md)。

各组件及第三方依赖的版权和许可证随源码保留，按对应文件约定使用。
