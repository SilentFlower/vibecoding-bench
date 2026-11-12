# 路径与工作流盘点

## 已核事实

- 源码：`deploy/v3/source_layout.py` 目前映射 services/apps/resources，部署自身目录尚无新旧映射。
- 固定包：`install_system_updater.py:30-41` 的SOURCE_FILES采用原逻辑路径；同文件72-75行的策略目标和138行的systemd入口指向宿主source/deploy/v3。
- 读取：安装器已通过source_path读取SOURCE_FILES，策略摘要仍有直接REPO/deploy/v3读取；manage的版本文件也是直接读取，构建快照仍应使用原逻辑路径。
- 底座归属：`upgrade_system_updater.py:80` 核验已安装服务的原固定ExecStart，目标路径需继续沿合同。
- CLI：`scripts/v3-stack` 当前直接执行deploy/v3/manage.py。
- 网关：仅两份嵌套workflow，当前根CI未使用workflow_call或uses引用。其内容是独立仓的自动Docker推送和多平台独立Release，旧前端目录与新单仓布局不符。
- 根CI：`v3-build.yml`、`v3-release.yml` 的实际源码调用以及缓存action的版本文件指纹需同步。工作流文件名作为原发行身份继续保留。
- 官方位置约定：[GitHub Actions workflow语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#about-yaml-syntax-for-workflows)规定工作流位于仓库.github/workflows目录。

## 检查归类

当前可执行源码路径、固定宿主包逻辑路径、历史资料三类分别核对。采用针对消费者的迁移，保留固定包及历史身份。旧版源码、上一版单仓源码与新目录源码的读取均需夹具覆盖。
