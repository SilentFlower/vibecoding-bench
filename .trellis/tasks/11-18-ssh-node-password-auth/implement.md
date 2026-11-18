# 实施计划

## 顺序

- [x] 加载编排、前端和镜像规范，核对相关模型及调用签名。
- [x] 扩展 cluster_nodes.py、cluster_service.py、cluster_store.py 的认证方式、只写凭据和公开投影。
- [x] 扩展 cluster_ssh.py 的密码持久化、独立描述符认证及命令/隧道进程清理。
- [x] 在 images/v3/Dockerfile 的 control 目标补充 sshpass。
- [x] 扩展 Nodes.vue 和 runtime/nodeApi.ts，覆盖认证切换和秘密清理。
- [x] 补充安装配置缺失提示，以及 deploy/flower2api/CLUSTER.md 的接入与宿主模板维护说明。
- [x] 扩展 test_cluster_nodes、test_cluster_ssh、test_cluster_deployment，必要时新增聚焦测试文件。
- [x] 完成质量检查、规范沉淀及精确提交计划。

## 验证

- 按现有 Python 环境执行 test_cluster*.py 测试集，重点验证认证、公开投影、权限、失败清理和旧配置。
- 隔离真实 sshd 使用合成密码，覆盖指纹拒绝、特殊字符、标准输入、三类独立隧道、Docker SDK 及进程收口。
- 按 apps/web/package.json 执行类型检查和构建，浏览器验证提交字段、方式切换和离开清空。
- 核验正式 control 目标的 sshpass 依赖，执行 git diff --check。

## 操作边界

本任务在 Brief 审核通过后进入实现。原 main 节点保留密钥认证。实际发行及 US 生产维护按独立授权续接，维护候选与恢复材料保留在原 root 私有目录。隔离验证结束后回收本次容器、进程和 socket。

## 验证结果

- 集群测试 555 项：550 通过、5 项按开关跳过。密码真实 SSH 4 项另行开启通过。
- CHK-001 已修复：新密钥配置由实际 HEAD 版本读取器读取成功；31 项存储、SSH 和备份定向回归通过。
- 前端类型检查及生产构建、两种视口的密码表单验证、部署工具 23 项、数据库 bench4/gateway4 和差异检查通过。
- Check-All 重检通过，剩余 CHK/FBK 为零。US 受信模板维护与实际 main 组件准备保留为上线后验证。
