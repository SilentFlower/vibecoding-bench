# DMI 常规读取的规划实验

## 范围

实验仅使用本机缓存镜像 `vibebench-v3-account:v3-quota-hard-stop-20261018-b`、临时目录、合成字符串和一次性 Docker 容器。容器无网络、根只读、cap-drop ALL、no-new-privileges；读取进程使用 UID1000。没有真实账号、凭据、宿主 Docker socket 或生产目录挂载。

本次没有修改产品源码；读取原型复制现有 `images/account/system-profile.c` 到 `/tmp`，仅加入两种 DMI 文件路径到临时只读文件的白名单映射，再用缓存镜像中的编译器构建。该副本不作为待交付实现。

## 直接挂载

基线中两类 DMI 目录均不存在。分别尝试挂载 `/sys/class/dmi/id`、`/sys/devices/virtual/dmi/id` 及两者同时挂载，均在 OCI 创建挂载点阶段因 sysfs 只读而失败，退出码 125。

该结论仅证明不能把直接 bind 作为所有支持宿主的唯一实现；不声称所有 Linux 宿主上均无法挂载已有 DMI 目录。

证据：`dmi-mount-probe.json`；原始路径 `/tmp/v3-fingerprint-dmi-planning-result-20261020.json`。

## 文件覆盖原型

原产品 C 文件 SHA256：`bce76b83e2c7d477d70629ba3c825a8dc7ea91f871aa98483b29b77ab6a1fbbd`。

| 入口 | `/sys/class/dmi/id/product_name` | `/sys/devices/virtual/dmi/id/product_name` |
|---|---|---|
| Python pathlib 内容读取 | 返回合成产品值 | 返回同一合成产品值 |
| cat 内容读取 | 返回合成产品值 | 返回同一合成产品值 |
| Node fs.readFileSync | 返回合成产品值 | 本次原型未单独调用此别名 |
| Python exists／access | false | false |
| Shell test -r | 失败 | 失败 |
| Node existsSync | false | 本次原型未单独调用此别名 |

内容读取已证明可沿用当前动态库机制，但元数据与可读性检查尚不一致。因此实施必须纳入必要 stat／access 等动态入口；本实验不能替代两目录六字段及元数据的完整验收。

首次编译因缺少可写编译临时盘而失败；增加专用 noexec 临时盘后通过。首次加载因临时父目录默认 0700 导致 UID1000 无法遍历而失败；设为 0755 后通过。正式渲染同样需要保护文件所有权和目录可遍历权限。

最终读取进程退出码 0、无加载错误，实际结果保存在 `dmi-read-probe.json`，原始路径 `/tmp/v3-fingerprint-dmi-routing-result-20261020.json`。所有临时容器均通过 `--rm` 清理，实验目录保留用于核查。

## 方案影响

- 不扩大权限、不替换整棵 sysfs，使用受保护只读画像和精确路径覆盖。
- 把内容、元数据、权限检查及支持的相对读取作为一个验收面，避免只验证页面或 cat。
- 继续按当前契约报告静态程序、直接 syscall、CPUID 等边界。
