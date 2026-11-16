# 清理证据

- 当前源码基线：e62d82926937be1cb9bf5b9a0f1f66a213f959c4，branch flower2api。
- main注册提交：6f1b24bf866831d82808d54b4f0a9f48f7c35f41。
- main旧发布入口：.github/workflows/docker-publish.yml，workflow_dispatch且仅main，矩阵orchestrator/worker/sidecar。
- 部署读检查：两份.deploy配置为同一SSH身份，15个容器，匹配三个旧镜像引用0；执行仅docker ps -a，原始安全汇总位于.trellis/.runtime/flower2api-image-lifecycle/host-reference-check.json。
- 本机包列表GET：HTTP403，message=You need at least read:packages scope to list packages。
- 官方权限与恢复依据：https://docs.github.com/en/packages/learn-github-packages/deleting-and-restoring-a-package 。仓库若具备包admin权限，可通过GITHUB_TOKEN调用包REST；权限预览失败保持停止。
- 正式两镜像的精确名称为现有签名校验的一部分；三个旧包与两项正式包分开治理。

## 实际远端清理

- 预览运行43247664483，应用运行43248120634，源码0fad8e42e896d16a237695d29c13f24dccf83b1b；两运行成功。
- 冻结摘要4d98ac8e8a70aa9c3f979a59741b3550891dff7ed865adc1ee3a84d46548ede4。
- vibebench-orchestrator：ID=13482959，版本465，DELETE=204且复查404。
- vibebench-worker：ID=13482972，版本445，DELETE=204且复查404。
- vibebench-sidecar：ID=13482966，版本450，DELETE=204且复查404。
- 共清理1360个旧版本；固定白名单外的正式包进入保护范围。原始安全计划与逐项收据保存在gitignored运行证据目录。
- main工作流注册已与实际提交e7fb0678c6f7652514c4de8a573752f3b097c21b逐字核对。对应业务源码的构建43247609752成功，联合清单dirty_worktree=false、两角色齐全，固定原生制品SHA保持。
