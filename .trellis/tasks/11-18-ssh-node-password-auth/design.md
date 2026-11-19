# 设计

## 配置和页面

NodeConfiguration 增加 auth_method，允许 private_key/password，默认 private_key。NodeCreate 的 private_key/password 为排除序列化及 repr 的只写字段，校验材料与方式唯一对应。ClusterService.register 从脱敏 model_dump 构造配置。密钥节点持久化省略默认 auth_method，保持已发布严格读取器的字段集合；密码节点显式持久化 auth_method=password。ClusterStore._public 显式投影认证方式；本机为 null，历史 SSH 配置默认私钥。沿用 JSON 配置，无需数据库迁移。

表单使用现有 ChoiceSelect 选择认证方式，密码采用掩码输入；切换时清空隐藏材料，成功、关闭和卸载时清空两种秘密。保留主机公钥探测与显式核对。

## SSH 认证和生命周期

沿用 OpenSSH，为 control 目标安装 sshpass。密码沿现有安全目录与原子写入工具保存为 0600 私有文件。每次连接用 O_NOFOLLOW 打开，fstat 校验常规文件、当前 UID 和权限；sshpass 通过独立只读文件描述符读取，子进程仅用 pass_fds 继承该描述符，父进程启动后关闭。密码不进入 argv、环境或业务 stdin。

密钥分支沿原参数。密码分支限定 password、一次密码提交并关闭公钥与键盘交互回退。两路继续固定 known_hosts/HostKeyAlias、StrictHostKeyChecking，禁用 agent、代理和用户配置。

命令和三类独立隧道共用认证构造。保持原 I/O 预算和超时，sshpass/OpenSSH 失败映射为固定中文错误。新增父子进程须按本次进程组收口，超时、转发失败、close 均释放所属进程与 socket。

## 安装诊断与运维

在进入安装前检查 NodeDeployment 必需中央配置，缺失时仅返回配置项名称。保持安装门禁及记录归属。仓库 compose 已定义 V3_CONTROL_IMAGE、V3_RUNTIME_URL；旧固定宿主模板需按 SYSTEM-UPDATES.md 专项维护刷新。US 的候选仅增加这两项，其余渲染配置完全一致；实际维护等待独立授权。

## 兼容与验证

旧私钥节点及请求直接兼容。密码节点依赖新控制程序与 sshpass，回退旧程序前须收口密码节点及其账号引用。中央凭据备份沿现有 cluster-private 权限保留。

真实密码测试使用隔离 sshd 和合成账号，避免修改开发宿主和生产账号密码。覆盖 stdin、独立转发、实际 Docker SDK 模拟 API、清理和秘密保护，前端执行类型检查、构建及浏览器验证。
