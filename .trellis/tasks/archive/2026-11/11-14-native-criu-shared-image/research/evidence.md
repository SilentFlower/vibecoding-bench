# 研究依据

## 已验证

112843960字节合成执行体，四份分配430.469 MiB，共享一份为107.617 MiB。四个进程保留独立私有计数，一进程退出后其余继续响应。四个MAP_PRIVATE映射独立写入1/2/3/4，背板保持零；原FD关闭且一个退出后，其余保持2/3/4。

seal=15拒绝共享写映射和重复加seal。相同名称可以有不同inode。四项seal下权限模式仍可变。

研究版CRIU仅增加exe继承路径后make -j4 criu WERROR=1通过。本地快照报suspending seccomp failed: Operation not permitted。

## 源码事实

CRIU4.2每次恢复重建memfd，fdstore缓存属于本次恢复。FD/VMA支持inherited_fd，当前项目prepare_mm补丁直接调用memfd_open。继承按名称匹配，并跳过原FD的fown和偏移恢复。

固定归档SHA256：0c6e51af878e63df7391e6dffbbe5f0ced429bc9f1e5a603020bfd2503065c39。

## 私有材料定位

.trellis/.runtime/criu-image-sharing-research/下的research.md、kernel-result.json、risk-probes.json、compile.log、dump.log、experiment.log保存原始证据。任务只保存脱敏汇总。

## 官方来源

- https://github.com/checkpoint-restore/criu/blob/v4.2/criu/memfd.c
- https://github.com/checkpoint-restore/criu/blob/v4.2/criu/files-reg.c
- https://github.com/checkpoint-restore/criu/blob/v4.2/criu/files.c
- https://man7.org/linux/man-pages/man2/memfd_create.2.html
- https://man7.org/linux/man-pages/man2/mmap.2.html
- https://man7.org/linux/man-pages/man2/F_ADD_SEALS.2const.html
