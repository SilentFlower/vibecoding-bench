# 人工分配节点与统一网关

管理员决定账号位置。客户端继续使用中央 API 地址及原令牌。每个账号的 network、CLI、sender、HOME 和工程目录在所属节点，SSH 同时承接控制和独立业务隧道。

## 接入

1. 准备长期在线、中央可达的 Linux x64 服务器及 Docker。节点用户须有 Docker 权限。认证可选择专用 SSH 私钥或该用户的 SSH 密码。密码方式要求目标 SSH 服务启用 password 认证；键盘交互和二次认证属于独立认证方式。Docker 权限等同宿主管理权限，认证材料按管理凭据保管。
2. 在节点的可信终端运行 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256`，取得实际主机指纹。
3. 后台进入“节点”，填写 SSH 地址、端口、用户和独立数据根，选择“SSH 私钥”或“SSH 密码”并填写对应材料。密码按原值使用。探测后对照可信终端的指纹，确认并保存。更换主机密钥前先排空旧连接，再登记已核对的新身份。
4. 点击检查和准备运行组件。中央通过 SSH 交付当前两类镜像，安装私有 Node 控制实例并核对实际内容、协议、部署与批次。认证材料仅写入中央私有目录（目录 0700、文件 0600），公开接口只显示认证方式。密码通过独立文件描述符交给 sshpass，业务标准输入继续用于节点命令。备份须保留私有目录权限。
5. 创建账号时选择节点。已有环境使用“迁移到所选节点”。单独修改账号配置保持现有节点归属。

节点仅需要 SSH 入站。SSH 服务须允许本任务使用的本地 TCP/Unix socket 转发。Docker API、Node 管理接口及账号 sender 端口留在私有网络。跨机加密由 SSH 提供。

### 旧部署的中央配置核对

节点安装读取中央控制进程的 `V3_DEPLOYMENT_ID`、`V3_RELEASE`、`V3_CONTROL_IMAGE` 和 `V3_ACCOUNT_IMAGE`。中央编排服务还需采用部署模板中的 `V3_RUNTIME_URL=http://orchestrator:8000`，用于节点传输回连。缺少安装必需配置时，准备接口会显示具体配置项名称。

固定宿主更新器持有独立的受信 Compose 模板。应用镜像升级后仍需核对该模板及实际容器环境。旧模板缺少节点配置时，按 [系统更新维护流程](SYSTEM-UPDATES.md#单部署镜像与容器名称切换) 保存原始字节，核对策略摘要和资源配置，在原服务锁及存储锁内同步受信模板，并通过原门禁排空、重建控制端。现有账号资料与 CPU/RAM 配置继续沿原合同保留。

历史节点缺省使用私钥认证。密码节点要求中央采用包含 sshpass 的新控制镜像。回退到旧控制程序前，先完成密码节点的账号迁移及引用收口，再处理该节点登记。

密码认证的隔离验收使用合成账号和仅映射回环端口的容器：

```bash
docker build -t flower2api-ssh-password-test:local deploy/flower2api/fixtures/ssh-password
CLUSTER_SSH_PASSWORD_TEST=1 PYTHONPATH=services/orchestrator:deploy/flower2api \
  .venv/bin/python -m unittest test_cluster_ssh_password
```

可用 `--build-arg CONTROL_IMAGE=实际控制镜像` 复用目标批次的基础环境。测试结束自动回收本次 sshd 容器和临时凭据。

暂停节点会关闭新工作准入。查询、原操作停止及凭据交接收尾继续核对原归属。节点离线时受影响账号显示待核对，其他节点独立运行。恢复连接后先处理原执行收据和实际进程。

## 本机操作模板

下列命令在对应 Node 执行。`NODE_DATA` 是后台登记的数据根，`CONTROL_IMAGE` 是本批固定控制镜像。辅助容器使用原 control 镜像，省略 Node 归属标签，避免把辅助容器计入运行角色。首次安装、换批和协议核验由中央节点页面的“准备”完成。

```bash
NODE_DATA=/srv/flower2api-node
CONTROL_IMAGE=ghcr.io/silentflower/flower2api-control:v3-替换为实际批次

# 将 status 换为 check 可以核对安装、角色及控制实例挂载。
docker run --rm --network none --entrypoint python3 \
  -v "$NODE_DATA:/data" -v /var/run/docker.sock:/var/run/docker.sock \
  "$CONTROL_IMAGE" /app/cluster_node_ops.py status \
  --data-root /data --host-data-root "$NODE_DATA"

# 先在中央暂停新工作并排空，再停止该 Node 的账号、独立验收和控制实例。
docker run --rm --network none --entrypoint python3 \
  -v "$NODE_DATA:/data" -v /var/run/docker.sock:/var/run/docker.sock \
  "$CONTROL_IMAGE" /app/cluster_node_ops.py stop \
  --data-root /data --host-data-root "$NODE_DATA"

# 同批恢复只启动原控制实例，账号由原生命周期恢复。
docker run --rm --network none --entrypoint python3 \
  -v "$NODE_DATA:/data" -v /var/run/docker.sock:/var/run/docker.sock \
  "$CONTROL_IMAGE" /app/cluster_node_ops.py up \
  --data-root /data --host-data-root "$NODE_DATA" --release 替换为实际批次
```

## 迁移与恢复

源和目标须在线。迁移先关闭原账号的新准入并排空 API、CLI、终端、评审、授权与凭据维护，再停止源角色，传输并核对身份和持久资料，最后切换归属并激活目标。独立账号保持当前 Node HOME 的 RT，绑定账号保持 Gateway 唯一刷新权与 Node AT-only。

提交前可以继续原操作或取消。取消先核对并停止目标副本，再恢复源归属。提交后的恢复继续激活目标。界面保留操作 ID、最后确认阶段、当前处理步骤、固定失败原因及恢复动作。原迁移的文件数、清单总大小和导入耗时按实际资料处理；大 profile 经私有摘要文件传输。源身份、路径、摘要、实际磁盘容量与租约仍逐项核验。未知输入、RT 提交或迁移结果按原收据核对。

## 集群离线备份

中央备份保存中央数据库、账号管理资料、归属、迁移账本及节点认证。Node 备份保存其当前 HOME、工程资料与执行数据库。完整集群恢复需要同一停机批次的中央与全部已登记 Node 备份。

1. 暂停新调度和节点接单，收口或停止在途任务、授权和评审。依次停止所有 Node，核对独立验收容器退出，再停止中央。存在未知操作时保留其原账本与现场。
2. 全部停止后生成一个 32 位小写十六进制批次，例如 `python3 -c 'import uuid; print(uuid.uuid4().hex)'`。各服务器使用同一个 `EPOCH`。
3. 每个 Node 将备份写入数据根之外的全新目录。以下 `BACKUP_PARENT` 是独立私有备份父目录，`EPOCH` 由上一步给出。

```bash
BACKUP_PARENT=/srv/private-node-backups
docker run --rm --network none --entrypoint python3 \
  -v "$NODE_DATA:/data" -v "$BACKUP_PARENT:/backups" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "$CONTROL_IMAGE" /app/cluster_backup.py backup \
  --data-root /data --backup-dir "/backups/$EPOCH" --epoch "$EPOCH"

# 在中央执行原备份入口，保留配置及完整恢复资料。
scripts/flower2api-stack backup --env /absolute/path/v3.env \
  --backup-dir /absolute/path/new-central-backup --full --cluster-epoch "$EPOCH"
```

4. 将所有备份按原权限、UID/GID、链接复制到隔离校验目录。使用完整仓库及原 Python 依赖执行组合校验，每个 Node 重复一个 `--node-backup`。

```bash
python3 deploy/flower2api/node_backup.py verify-cluster \
  --central-backup /isolated/central \
  --node-backup /isolated/node-a --node-backup /isolated/node-b
```

组合校验执行实际隔离复制、文件摘要、权限/链接、SQLite 完整性及逻辑内容校验，并核对部署、批次、Node 安装身份和账号归属。`pending_operations`、`reconcile_required` 记录需要沿原状态恢复的事项。验证通过代表备份资料完整，恢复后仍须处理原待确认操作。

恢复先使用全新隔离目录核验整组资料。实际恢复须在全部服务停止时进行，保持每台服务器原安装身份、Node 数据根和中央 SSH 认证材料。启动中央后按同批组件核对节点，再处理原待确认操作。Node 当前 HOME 是独立账号的刷新材料来源。备份含秘密，按原私有权限保管。

## 升级与回退

当前控制端会自动同步已托管节点。首次接入使用“准备运行组件”；已有组件使用“检查并同步组件”，也可在顶部点击“同步全部节点”。操作在后台执行，页面显示核对、等待工作、备份、切换和恢复阶段。节点原有接单偏好保持。

- 同批只复核实际镜像、归属和健康状态。
- 旧批次自动等待原工作及凭据维护收口，停止本节点角色，生成数据根之外的完整私有备份，再切换控制组件并恢复账号。只更新控制组件时，相同账号镜像复用原角色和代次。账号镜像变化时沿原生命周期重建，HOME、设备身份和工程资料继续保留。
- 暂时断线保留原操作并后台重试。未知角色、未完成目标副本及凭据交接显示具体等待原因。原迁移先完成后自动同步。源已隔离且目标尚无副本时，可先同步空目标，再继续原迁移。
- 平台在线更新在原维护操作内收集同代 Node 完整备份。中央切换后继续同一节点作业，全部节点通过健康核验后再恢复接单。更新页显示逐节点进度。
- 失败恢复沿原控制及完整快照收口。恢复旧快照时，将切换后资料移入私有隔离目录。已重新接单后的恢复沿当前资料执行反向组件切换。

备份保存在登记数据根旁的 `<数据根>-backups/<节点作业ID>/snapshot`，包含账号私有材料，按原私有权限保管。备份及隔离资料在恢复核对完成后按维护流程处理。

历史中央版本缺少内部节点维护接口时，首次跨版本升级仍使用本文件的全体停机和同代备份流程，配合 [系统更新 SOP](SYSTEM-UPDATES.md) 完成中央升级。进入本版后由后台统一同步节点。协议和实际归属存在冲突时保留原记录，沿原作业核对。

回退到具备集群协议的兼容版本，同样全体停机并按目标批次核对。回退到集群功能之前，先在当前版本将远程账号迁回默认节点并完成所有权收口，再执行原回退 SOP。恢复旧快照须成组恢复中央及 Node，避免旧中央账本与后来的 Node HOME 混用。
