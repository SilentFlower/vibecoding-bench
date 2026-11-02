# 旧部署永久退役

## 目标与来源

在 9-17 迁移和验收成功后，永久删除旧版服务、对应无引用镜像和旧挂载数据，退出旧业务入口。覆盖父需求 R7–R9。用户已明确选择“删除吧 不归档了”，授权包含旧账号资料与全部旧历史，不再要求保留旧版可查。

## 精确范围

- 旧容器 `vibebench-orchestrator`、`docker-claude-code-gateway-1`；执行前重新识别确属同一旧部署的 worker/sidecar，拒绝未知或共享资源。
- 上述旧部署对应、已冻结并核对全部容器引用的旧镜像及其标签/digest；只删除无保护引用的目标。
- 旧 bind 数据 `/root/vibecoding-bench/data`，以及实际检查确认无共享引用的旧挂载 `topics.md`、`webui`；不整目录删除宿主源码仓库。
- 两个旧部署目录内经实查确认的旧数据库、镜像归档、配置备份和部署暂存副本一并删除：bench 的 `backups/.deploy-backups/ops-backups/.deploy-backup/.deploy-staging/.deploy/.capture-audits`、旧 `.env` 与其历史副本、旧挂载/Compose 历史副本；gateway 的 `backups/.deployment-backups`、父目录和 docker 目录旧 `.env` 及 Compose 历史副本。执行前冻结真实文件名，不用宽泛通配删除；保留源码父目录、Git 与当前公开源文件。
- 旧 gateway 命名卷 `docker_claude-code-gateway-data`，通过 Docker 删除，不直接操作 Docker 私有存储目录。
- ai-fund 旧 5674 来源退出并清理失效配置/凭据；下游仍指向旧地址的渠道只做退役所必需的停用或等价切换，保留既有分组/模型/额度边界。

## 验收

- T1：迁移通过收据存在且与当前目标账号/环境一致；不能仅凭旧快照或用户概括授权跳过迁移验收。
- T2：消费者已退出旧入口、旧服务无在途工作，资源归属和全部引用核对通过才删除。
- T3：旧目标容器和指定旧挂载不存在，命名卷已删除，合格旧镜像实际回收；无旧数据库、历史或凭据归档副本。
- T4：现有 v3、其他应用、共享挂载及受保护镜像保持，页面/鉴权/数据库健康通过。
- T5：私有 plan/result 收据只含元数据与已完成事实，报告实际文件系统可用空间差，不累加镜像虚拟体积。

## 范围外

不删除当前 v3、其他应用、Docker socket/共享基础设施或 NewAPI 历史记录；不全局 prune，不强制删除仍有引用的资源，不新建备份归档。
