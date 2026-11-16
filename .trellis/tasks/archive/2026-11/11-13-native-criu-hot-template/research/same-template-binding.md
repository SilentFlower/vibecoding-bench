# 同模板恢复绑定与随机状态验证

## 环境与结果

隔离 KVM，Linux 6.12.115-0-virt，2 vCPU、3072 MiB；外部网卡关闭，HTTP 接收端位于独立回环网络。合成身份，遥测关闭。源进程与七副本均为 UID1001、CapEff0、NoNewPrivs1、Seccomp2；执行 memfd seals15。

使用本任务固定配方构建的 CRIU4.2（二进制 SHA a89e3774e4cf150440aaa99a9690e179aa325ecff43e07b38d579da5836cca65），新桥接执行体 SHA 564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79。源模板保持存活，串行三次、并行四次恢复全部完成实际 worker_restore_bind、新 worker_id/nonce 回执及各自一笔 HTTP 请求。bootstrap 为零 POST，业务总计七 POST。独立物理 PID、管道与目录核对通过。细项见 same-template-binding-summary.json。

## 随机状态缺陷与复位

未经处理的快照复制 Bun1.4.3 的线程原生 DRBG、2048字节 UUID 缓存与主 realm Math.random 状态。随机 UUID、禁用缓存 UUID、randomBytes 和 Math.random 在副本间出现重复。

固定画像下，受信控制器在全线程暂停并核验父进程、启动时刻、UID、能力、NNP、seccomp、实际执行体 SHA 后，仅清零 BoringSSL 唯一 MADV_WIPEONFORK 页首四字节 fork 标志。原生线程下次生成随机数时沿其自身 fork 处理重新播种。runtime 绑定阶段再丢弃129个 UUID 耗尽旧缓存，并读取 /dev/urandom 为主 realm setRandomSeed。Bun 版本、完整 revision、realm 数量与结构必须匹配。

实际产品 entropy.py 与 restore.ts 共同复位后的纯观测结果：普通 UUID224/224 唯一、无缓存 UUID224/224、32字节随机组56/56、Math.random224/224。该合同仅覆盖固定桥接业务使用的随机源；未覆盖任意动态 VM realm 或升级后的 Bun。

来源：Bun issue47213（https://github.com/oven-sh/bun/issues/47213），未合并 PR47282（https://github.com/oven-sh/bun/pull/47282）；固定 Bun revision eecfd55debb281c3fe3518098b1a49f76429637c，BoringSSL 依赖 revision 41bf9b59c2ebf277a7aa427e1ecad5cc80dd4d4f。

## 计时边界

串行 restore 为673.48/132.75/113.36ms，绑定为17.19/14.69/19.30ms。四并发 restore 为2204.93/2215.02/2189.74/810.35ms，绑定为93.16/27.23/23.67/442.06ms。本次 restore 口径包含 Python 受信执行体全量核验和线程检查；调度和冷读波动尚待拆分。这些数据属于隔离实验，完整池准备和实际 TLS 观测尚待完成；A7性能门槛保持待验。

## 工程交接

恢复控制器通过 SCM_RIGHTS 直接移交管道及命名空间 pidfd。先移交命名空间存活句柄，sender持有后才ACK启动恢复；断开由控制器结束命名空间，sender等待pidfd实际退出后归还物理许可。模板来自池预算内后台零业务补位种子，dump完成后种子绑定成普通暖进程；模板保留冻结目录副本和同账号稳定代理引用。实际TLS归属经控制器登记表传给现有采集broker。
