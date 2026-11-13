# 实施计划

## 顺序

- [x] 1. Brief交接后激活任务，进入trellis-route，读取规范与实际类型，保留397项既有脏基线。
- [x] 2. 补做FD语义和同名歧义实验，检查真实CC执行体FD与VMA形态。
- [x] 3. 更新权威CRIU补丁，覆盖FD/VMA/exe共享身份、seals、权限和私有页，编译并做恢复对照。
- [x] 4. 更新Controller.Template、launch.c和supervisor.py的源FD持有、独立打开及移交，覆盖退出、撤销与取消。
- [x] 5. 加强Rust实际inode准入，保留nonce、随机重置、TLS、许可与唯一投递；失败回退普通exec。
- [x] 6. 更新配方摘要、画像、预检和说明，通过export_bundle同步镜像输入。
- [x] 7. 补充身份、FD、权限、生命周期和回退故障回归，完成Python、C和Rust检查。
- [x] 8. 在支持CRIU的隔离环境完成真实CC四路及连续请求验收，记录内存与延迟，逐项记录环境阻塞。
- [x] 9. Check-All后更新合同并生成精确Push计划，按实际验收状态报告。

## 验证

- python3 -m unittest discover -s services/runtime/native/criu -p 'test_*.py'
- python3 -m unittest discover -s services/runtime/scripts/criu -p 'test_*.py'
- 对新增FD身份、碰撞、清理和回退执行定向回归。
- 在目标ABI隔离依赖环境运行services/runtime/scripts/criu/build.py，使用已核验归档和全新输出。
- export_bundle.py导出到全新目录，逐文件核对镜像输入和source-manifest。
- 固定C加载器沿-O2 -Wall -Wextra -Werror -Wl,-z,relro,-z,now编译。
- services/gateway：cargo fmt --check；cargo test --locked。
- 恢复验收记录物理PID、exe/VMA dev/inode、seals、版本、来源和请求结果；统计current/peak、anon/file/shmem，避免对子集shmem重复求和。
- 合成身份、快照和请求材料留私有runtime，任务保存脱敏汇总。

## 风险与回退

memfd补丁重点检查三条恢复路径与私有页。Controller/launch/supervisor重点检查FD所有权、ACK、pidfd和清理。Rust重点保持摘要/seals准入与真实退出后释放许可。配方、画像和入口预检需同步，新旧不匹配走普通exec。预算保持现有值，部署另行安排。

## 验收停止条件

- 完整CRIU恢复、原生请求或故障回退证据缺失时，对应验收保持未完成。
- 本地权限阻塞记录为环境事实，不能替代恢复验证，隔离限制按原合同执行。
- 新生产、凭据、付费或外部操作按具体授权边界处理，先完成可离线验证的实现与证据。
