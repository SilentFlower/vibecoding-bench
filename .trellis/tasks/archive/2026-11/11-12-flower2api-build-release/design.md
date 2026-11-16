# 构建与发布解耦设计

## 范围与入口

现有 `.github/workflows/v3-build.yml` 的 build job 同时持有 contents/packages 写权限并执行全部发布动作。拆分为两个可独立操作的工作流：

- `v3-build.yml`：v3/flower2api push、目标分支 PR、workflow_dispatch。保留 Python 3.12、现有依赖安装、合同和迁移单测、两个正式镜像构建、本地清单及验证 artifact。权限 contents:read；不读取发行私钥，不登录或推送 GHCR，不调用发布入口。构建 artifact 为诊断材料。
- 新 `v3-release.yml`：仅 workflow_dispatch；手动选择 v3 或 flower2api，并通过显式 publish 输入确认发布。同一 runner 从当前 GITHUB_SHA 检出、复验、构建、完成真实兼容演练、推送镜像、上传完整附件和推进受信目录。避免跨 run 复用不明构建结果。只有此 job 持有必要 contents/packages 写权限。
- `docker-publish.yml`：旧 main 镜像交付保留手动入口，删除 push 发布触发，并在 job 再次校验事件与 ref。

构建与发布入口共用现有验证命令及 deploy/v3/manage.py 构建函数。小范围必要的 YAML 步骤复用以可读性为先；静态验证比较关键验证步骤，避免引入通用流水线框架。

## 发布来源和失败边界

- `deploy/v3/manage.py:publish` 与 `deploy/v3/publish_system_release.py:publish` 的来源校验同步接受本仓两个明确分支，同时要求 GITHUB_EVENT_NAME=workflow_dispatch、手动发布入口身份及显式发布标记。
- 保留完整 SHA、唯一 run/attempt、clean 来源、镜像身份、digest 和临时路径校验；其它事件/来源在 docker push、gh release、目录写入前失败。
- 手动发布在昂贵构建及外部写入前检查签名配置。缺少有效签名材料应明确失败，避免产生只有镜像而没有可安装发行的半完成流程。
- 正式发布继续执行现有真实数据库兼容验收，证据与候选镜像、源码及原发行绑定；失败禁止签名目录更新。
- v3/flower2api 的受信发行共用 `v3-signed-system-release` 并发组，保留 cancel-in-progress:false 与普通 fast-forward 目录推送。

## 连续发行序号

旧实现用 `[GITHUB_RUN_NUMBER, GITHUB_RUN_ATTEMPT]`。GITHUB_RUN_NUMBER 按工作流从 1 计数；拆分后可能小于既有签名目录，从而使发布被视为旧发行。参考 [GitHub 变量文档](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)。

在现有共享发布串行区内，先用同一信任根读取并校验目标目录与需继承的旧目录，按签发时刻验证历史过期目录。以已验证目录的最大 sequence[0] + 1 作为新发行主序号，第二项保留实际 attempt；首次目录从 1 开始，严格受现有安全整数上限约束。损坏/来源不符的目录停止发布，404 才按既有首次路径处理。发行名继续使用 run_id/attempt，不由序号派生。

当前 run/attempt 已有同名发行时按既有不可覆盖边界拒绝重复；重试使用新的 attempt。新目录仍引用原签名旧发行，晚到的旧语义版本继续被 ensure_forward_version 拒绝。fast-forward 冲突按现有失败合同保留事实。

## v3 原地升级兼容

- 保持 `SilentFlower/vibecoding-bench`、`ghcr.io/silentflower/vibebench-v3-control|account`、`system-ci-*` 与 `v3-ci-*`，以及 updates/v3-migrations、updates/v3 的既有语义。
- 保持 Ed25519 信任根、发行 schema、兼容协议、数据库合同、部署标签与原数据根。开发分支名不进入宿主兼容判定。
- 严格使用现有验证器读取候选发行；保留旧库兼容演练及 v1 历史目录刷新。
- 日常操作为管理员在原系统更新页检查、准备、安装；保持原账号及环境身份、项目数据、历史和回退点。早期底座接入继续通过既有原地补齐 SOP。
- 当前本地版本元数据为 v1.1.0；本轮修复按规则准备后继补丁版本 v1.1.1 及准确说明。发布时仍与受信目录核对版本递增，拒绝覆盖后来版本。

## 生效与分步交付

代码首先在 flower2api 验证。CI 触发规则来自发生事件的分支，因此停用 v3/main 的旧自动发布需要把对应工作流修复同步至这些分支。此步骤须在后续 Git 计划中展示精确提交和目标分支。

仓库默认分支经只读查询为 main。GitHub 的手动入口展示依赖默认分支中的工作流定义；新入口需同步注册到默认分支，发布执行仍选择 v3/flower2api 并核对实际 SHA。参考 [GitHub 工作流事件文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)。

本轮仅准备代码和验证材料；远端发布、签名目录推进与线上安装属于后续明确动作。源码归并、品牌和界面在后续小版本实施，统一受 R4 原地升级约束。

## 固定宿主源码包依赖

manage.py 新增共同发布来源模块依赖；install_system_updater.py 的精确 SOURCE_FILES 同步包含 release_ci.py 和既有 platform_version.py。仓库外复制该清单后，以隔离 Python 导入 manage/system_updater 验证可用性，防止开发树路径掩盖接入包缺件。既有宿主已安装代码仍沿原固定来源执行，后继镜像升级继续复用原宿主协议。

## 验证与回退

离线边界测试记录 docker/gh/git 调用，确保错误来源零外部发布；真实临时 Ed25519 验证旧目录与新发行兼容、序号衔接、失败和并发保护。静态检查覆盖事件、ref、权限、秘钥使用位置和实际发布步骤可达性。

保持现有组件与数据迁移协议，可单独回退本轮构建发布代码。回退工作流时仍保持显式发布事件门槛，防止恢复自动发布行为。生产安装回退沿原系统更新合同。
