# 已核对的提速基线

- 来源源码：e3bd1db9d2fc4da80dd0fa7b27549a06ecbc70ab，v1.17.2。
- 构建：https://github.com/SilentFlower/vibecoding-bench/actions/runs/44301487648 。候选就绪442秒；control Docker构建217.409秒，account 24.110秒；job522秒包含缓存post。
- 发布：https://github.com/SilentFlower/vibecoding-bench/actions/runs/44302701047 。job478秒，可安装边界475秒；候选消费94秒；八个真实历史来源双路演练243.6秒；推送/打包51秒；签名发行和目录57秒。
- 从构建创建到可安装939秒。上次相同口径1031秒；正式发布job上次1110秒。
- 单来源实际耗时：72.399、66.727、59.318、56.622、61.268、58.300、50.068、50.060秒。源码中的模拟单测也会输出性能事件，以上只取正式发布运行。
- 前端版本入口：apps/web/src/lib/platformVersion.ts:3，两个消费者为Dashboard与SystemUpdates。
- 编译耦合：images/v3/Dockerfile:9-11注入版本；:27复制dist到Rust阶段；services/gateway/src/handler/router.rs:1801通过RustEmbed嵌入。
- 容器上限：verify_database_compatibility.py:103，内存768MiB、PIDs128、无网络、只读、cap-drop和临时合成挂载。
- 本机已有多个隔离v3控制镜像，可用于相同对象2/4真实Docker对照；其历史记录如为合成必须标注构成。
