# DeepDiff离线资源校准

固定提交79e4379278b1cfdd8e9e3dccac364956908e8989；当前镜像Python3.12.15，网络关闭、UID1000、只读根、PID64、无swap、完整默认tests，未传`--runslow`、`-k`或删除测试。

首次512MB原生校准失败，实际容器`OOMKilled=true`；第二次只增加逐节点输出，明确终止于`TestDistanceCache.test_get_multithreading`。该原始测试创建30个线程、提交30,000个Future。第三次限制glibc分配arena仍未通过，失败原件均保留；没有把失败写成断言通过或收集为零。

上游pyproject明确要求NumPy2.2、Pandas3.0、Polars1.39等完整测试依赖，冻结wheel展开约283.59MiB，其中Polars runtime约167.19MiB。产品原生准备在内存计费的`/work` tmpfs创建venv，pip默认额外生成字节码；历史研究依赖挂载在只读宿主目录，不能直接把历史256MiB实测套用到这条不同的准备路径。

本次最小适配为pip安装显式`--no-compile`，保留精确原始wheel、所有源码与测试；执行本来就设置`PYTHONDONTWRITEBYTECODE=1`，因此不需要预编译缓存。第四次512MB完整原生校准通过：1,308主项中1,264通过、44项上游原有跳过，原生JUnit与收集合同一致，无OOM，容器已清理。保留已有后台线程限制和`MALLOC_ARENA_MAX=2`，不据此声称通用性能提升。

业务观察也使用每仓显式512MB配置，时限仍30秒／PID64；这是既有独立原生回归512MB容量以内的项目验证档案，未修改账号容量、并发名额、候选／评审资源或授权。业务256MB不足以容纳本仓完整展开依赖，不能故意造成准备失败，也不能删掉适用依赖来维持较小数字。业务是否通过由随后逐任务真实结果决定，本文的回归成功不替代业务准入。

独立证据：`calibration/attempt-001`至`attempt-004/deepdiff`；最终完整索引`seventh-native-baselines.json`。产品原生验证器现有3项定向测试在带Docker SDK的独立venv通过；宿主默认Python缺少Docker依赖的首次导入失败另保留在会话记录，没有算作产品断言失败。
