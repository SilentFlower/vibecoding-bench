# 共享执行映像离线验收

本目录仅用于自有一次性虚拟机。三个根入口会核对 /probe/.disposable-criu-guest 内容为 offline-synthetic-only。虚拟机关闭外部网卡，入口运行于仅回环的网络命名空间。身份、bearer、邮箱、请求与模型响应全部合成。

## 环境和输入

本轮为KVM、Linux6.12.117-0-virt、2vCPU、3072MiB；Debian Bookworm用户空间、Python3.12。控制器能力032c11eb、NNP1、seccomp0；业务UID1001、capability0、NNP1、seccomp2。

1. 通过 services/runtime/scripts/criu/export_bundle.py 导出源码，在与目标相同ABI环境按package.py构建 /opt/ccrb-criu，复制profile.json到/probe/bookworm-profile.json。
2. /opt/ccrb-tls-observer 使用固定正式TLS观测束。安装libbpf1、bpftool、iproute2、mount与openssl，以及CRIU动态库。
3. 将本目录夹具复制到/probe，创建一次性标记，复制正式BPF到/probe/production-filter.bpf，编译restricted-launch.c为/probe/restricted-launch。
4. /probe/ccrb-runtime使用固定beta.6分发体。其SHA为fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e。
5. 实际网关池测试使用 cargo test --release --locked --lib native_criu --no-run 生成的库测试程序，保存为/probe/gateway-tests。使用与客体兼容的动态加载器；本轮将宿主测试程序依赖置于/opt/criu4/lib，由account-sender-test调用。将包装器放入/usr/local/bin/account-sender并设置可执行权限。
6. 合成签署v0.1.0-beta.999发布目录到/probe/releases，包含runtime-release.json、runtime-release.sig和ccrb-runtime-linux-x64；公钥hex字符串JSON放/probe/test-public-key.json。私钥仅留一次性运行目录。
7. 挂载cgroup2；控制器验收会创建独立memory统计子组。

## 顺序运行

每轮使用独立磁盘副本，保持客体资产可恢复。根入口按以下顺序分别运行：

```bash
unshare --net -- /usr/local/bin/python3 -u /probe/controller_probe.py
unshare --net -- /usr/local/bin/python3 -u /probe/bookworm_entry_probe.py
unshare --net -- /usr/local/bin/python3 -u /probe/bookworm_death_probe.py
```

controller：前三个串行、四个并发，随后杀死种子继续恢复，并在最后实例中途撤销模板。九个实例各发两轮请求，第二轮为流式工具响应，另含一次业务中取消，共19个本地模型POST。独立TLS采集与实收逐笔比对，九个会话隔离；注入非法身份、ACK前后取消、非权威对端和模板过期。四路同时就绪时统计种子与四副本的实际exe inode、权限、业务执行体FD及cgroup内存。末尾执行映像FD/映射引用归零，shmem回到峰值时非映像开销基线。

entry：调用真实产品入口和优化版Rust测试，完成20组交替普通exec/CRIU恢复，逐个核对实际inode、绑定和TLS就绪；失效模板回退完整submit，接收端恰好收到一笔业务。调试版的SHA校验耗时会影响180秒总截止，性能验收必须使用release构建。

death：通过自有pidfd强退控制器，确认命名空间和恢复worker实际退出、种子仍存活。新入口清理遗留模板及实例，业务POST为零。

## 基线与证据

旧版本Controller、supervisor、launch及CRIU应整套匹配。运行旧路径对照时，向controller_probe.py的环境显式设置CCRB_TEST_EXPECTED_IMAGE_INODES=5。默认共享路径预期一个inode。基线与共享使用相同固定执行体、请求负载、CPU和RAM。

初轮保留源的七实例验收还验证了快照内容污染拒绝。其结果与本轮完整链路一起保存在私有日志；脱敏结论见上一层acceptance-summary.json。

原始快照、完整正文、证书私钥及二进制保存在gitignored runtime。公开材料只保留合成夹具与脱敏汇总。
