# flower2api

整合 Claude Code 网关、账号运行环境和工程任务编排的统一平台。管理后台、网关、编排服务与原生运行时源码在同一仓库维护。

项目沿现有 v3 持续升级。`flower2api` 分支继承原项目，源码整合来源和固定提交见 [迁移记录](docs/migrations/flower2api-sources.json)。

## 功能

- Rust 网关：API 鉴权、账号池、请求转发、用量和请求诊断。
- 账号环境：独立 HOME、代理、CLI、发送器及持久工作区。
- 工程任务：Pi 驱动 Claude Code，提供项目目标、终端交互、迭代和交付验收。
- 统一管理：Vue 后台连接网关与编排服务，工程与任务页面通过静态界面接入。
- 系统更新：签名发行、双库兼容演练、原地升级和受控回退。

工程库包含 100 个项目、600 个功能或缺陷修复目标，见 [工程目标库](resources/project-library/README.md)。题库见 [topics.md](resources/topics.md)。

## 目录

| 路径 | 职责 |
| --- | --- |
| [apps/web](apps/web) | Vue 管理后台 |
| [apps/legacy-web](apps/legacy-web) | 工程、任务和账号静态页面 |
| [services/gateway](services/gateway/README.md) | Rust 网关与账号池 |
| [services/orchestrator](services/orchestrator/README.md) | Python 编排、账号环境和工程执行 |
| [services/runtime](services/runtime/README.md) | 原生内核适配与诊断工具 |
| [resources](resources) | 工程库、题库和研究资料 |
| [images](images) | 镜像定义和角色入口 |
| [deploy/v3](deploy/v3/README.md) | 联合构建、部署、备份和更新 |
| [.trellis](.trellis) | 项目规范与开发任务 |

组件已整合为普通源码目录。布局和路径兼容机制见 [单仓说明](docs/migrations/flower2api-layout.md)。

## 构建与发布

普通 push／PR 运行 [联合构建验证](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-build.yml)。正式发行使用 [手动发布](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/v3-release.yml)，选择目标分支并勾选 `publish`。

本地从仓库根生成两个镜像和同批清单：

```bash
python3 deploy/v3/manage.py build --release local-001 --manifest releases/local-001.json
```

每次使用新的批次名和清单路径。部署配置、资源要求和启动命令见 [部署指南](deploy/v3/README.md)。

## 现有实例升级

已接入系统更新的实例，通过后台“系统更新”检查、准备和安装发行。原 v3 的部署路径、镜像标识、环境变量和数据身份继续沿现有合同使用。

首次接入更新器、旧底座升级、数据库保护和回退步骤，统一见 [系统更新 SOP](deploy/v3/SYSTEM-UPDATES.md)。生产安装按对应实例的维护流程执行。

## 本地开发

从仓库根执行：

```bash
# 管理后台
npm --prefix apps/web ci
npm --prefix apps/web run build

# 网关回归
cd services/gateway
cargo test --locked
```

编排服务的依赖、测试和模块导航见 [编排服务指南](services/orchestrator/README.md)。运行时的 Bun 工具链及合成预览见 [运行时指南](services/runtime/README.md)。更多验证入口见 [模块与命令](docs/migrations/flower2api-layout.md#模块与命令)。

## 来源与历史参考

- [组件来源与固定执行制品](docs/migrations/flower2api-sources.json)。
- [历史 bench 使用说明](README.legacy.md)：旧版部署、题库和抓包流程。
- [网关导入时的上游说明](services/gateway/README.upstream.md)：原项目介绍及贡献者信息。

各组件和第三方依赖的版权、许可证文件随源码保留，按对应文件约定使用。
