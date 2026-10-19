# 持久计算机指纹研究基线

## 规划时点的请求与阶段

- 本记录采集于规划阶段，当时仅修改任务文档；此处保留实施前基线，后续实施结果见 implement.md。
- 用户要求静态字段首次随机生成并持久固定，重启或重建不刷新。
- 规划研究只读取已有产物，没有运行 vm2api 的闭源二进制，也没有发送模型、遥测、额度或认证请求。

## 我们已有的实现

- `orchestrator/account_runtime.py:61` 的 `derive_v3_fingerprint` 使用独立随机值初始化 hostname、machine-id、MAC，并保存时区和语言。
- `orchestrator/account_runtime.py:271` 的 `_row` 优先读取已有环境行，仅环境首次创建时生成基础画像。
- `orchestrator/account_runtime.py:329` 的 `prepare_system_profile` 仅缺少 `system_profile` 时生成，随后验证、保存和渲染只读文件；已有损坏记录不能通过重新生成恢复。
- `orchestrator/account_isolation.py:187` 配置 CLI 专属的 `/proc/cpuinfo`、`/etc/v3-system-profile`、`/etc/ld.so.preload` 只读挂载。network/sender 不加载这层覆盖。
- `images/account/system-profile.c` 覆盖常规动态 libc 的 uname 和指定内核文件读取。直接系统调用、静态程序、CPUID、未覆盖 sysfs 仍可能读取真实信息。
- 旧任务已确认的资源真实性和身份兼容边界见 `.trellis/tasks/archive/2026-10/10-17-v3-system-fingerprint/prd.md` 与 `research/coverage-and-options.md`。新请求扩展静态字段，不自动解释为授权更改资源预算或重置现有设备身份。

## vm2api 可验证的机制

研究提交：`819ee2a7c40b49fe81ebc3823e20373350a20545`，只读检出目录 `/tmp/vm2api-readonly-review-20261020`。

- `src/lib/identity/slot-computer.mjs:99`：有完整产物直接返回；否则调用 `kin-computer create --runtime docker|kvm --vm-id <id> --out <dir>`。
- 产物目录名为 `vms/<id>/kvm/fingerprint`，Docker 模式同样使用该目录；字段文件包含 `system/etc/hostname`、`system/etc/machine-id`、`system/hardware/mac` 和 `system/dmi/id`。
- `src/lib/vm/vm-runtime.mjs:783`：通过 Docker 主机名／MAC 参数及只读 bind 发布身份文件；DMI 目录挂在 `/etc/kin-dmi`。
- `src/lib/vm/guest-identity-reader.mjs:63`：采集脚本在目标容器内执行，读取 uname、os-release、procfs、sysfs 和环境变量；DMI 读取入口是 `/sys/class/dmi/id`。
- DMI 产物挂载位置与采集入口不同，不能仅凭目录存在宣称后者已经被替换；公开代码及测试替身不足以证明闭源产物的全部应用路径。
- `src/lib/vm/guest-identity.mjs:82`：合并采集值时保留部分已有身份；硬件空值可保留旧值。面板不是每次实时读取。
- `src/lib/admin/panel-api.mjs:231`：物理特征输出是已保存的 fingerprint、hardware、machine 配置等的组合，部分字段允许回退。
- `deploy/payload.json` 固定 `kin-computer` 的大小与摘要：5,527,768 字节，SHA256 `fa431f10321e6043ee88a4012b6dd8c515acac3a63fc40645091d1edf6334c01`。固定发布二进制不等于公开内部算法。
- `test/fixtures/kin-computer-stub.mjs` 明确只是测试替身，其稳定散列不能当作真实生成算法。
- 仓库根目录 `LICENSE` 是 vm2api 自定义许可，列有非商用使用及商用另行授权条款。若选择复用，其适用范围需按实际使用方式核对；本轮没有引入代码或分发产物。

## 已知生产基线

- 10-17：保存的 CPU 型号为 `AMD EPYC 7351 16-Core Processor`；10-19 为 `AMD EPYC 7401 24-Core Processor`。两者保存内核均为 `6.1.0-32-amd64`，现存 CLI 容器含对应只读挂载。
- 10-13 与 10-15 没有保存该 CPU／内核画像，不能把后续版本能力倒推到全部历史任务。
- 已停止容器的 inspect、宿主保存文件及 DB 可以证明配置，不等于本轮重新运行了容器内探针。

## 已确认决定

- 用户回复“我希望前者”，对应本项目独立实现相同字段与持久化行为；不接入闭源 `kin-computer`。
- 复用当前 CPU／内核覆盖及三角色隔离，增加缺失静态字段和对应常规读取支持；已有合法身份保留。
