# v1.7.0资源默认策略发行与上线核验

本轮交付默认无限内存与sender默认1.5核，并按追加指令正式发布v1.7.0。线上配置和安装沿后续操作指令与平台更新SOP执行。

- 部署：us，数据根/srv/vibebench-v3-us。在线版本v1.6.2，15个已登记环境。
- 将显式V3_ACCOUNT_MEMORY=1536m替换为unlimited，将部署V3_ACCOUNT_SENDER_CPUS设为1.5或移除旧覆盖以使用新默认。已有CPU持久策略继续优先。
- 安装前冻结配置、镜像及环境ID/代次，备份原配置；沿平台更新门禁排空，保护养号/项目/API及评审在途作业。
- 运行环境在空闲时迁移；停止环境保持停止，下次明确唤醒应用。
- 三角色及派生评审Memory=0/MemorySwap=-1，native memory_mib=0；sender默认1500000000 NanoCpus。
- 核对11-14原work 4a25e3e130634fd0a798d42e43427c33、session 1ade98d5-a0cf-4fae-9597-f8805942d35a以及1/600历史事实；新进度按真实执行事实保留。
- 核对实际请求内核、热进程和CRIU独立证据，保持零主动模型测试请求。
- 部分失败保留原配置、原环境或明确对账状态。恢复有限预算沿空闲重建，保护后来业务数据。

## 实际发行结果

- 正式版本：[v1.7.0](https://github.com/SilentFlower/vibecoding-bench/releases/tag/system-ci-43594047518-1)；发行身份`system-ci-43594047518-1`。
- 源码`f47fae4d2eeaf3b74f0ff770868c560afedbf3bc`；流水线43594047518全部通过。
- 双镜像源码摘要、6项附件及Ed25519签名独立核验通过。镜像包GitHub资产SHA256和大小与已签清单一致。
- `updates/v3-migrations`序号217/1，`updates/v3`序号196/1，两个目录的Git blob身份和签名通过。
- 8个历史来源的升级、候选读写、旧程序回退读写和幂等证据通过。
