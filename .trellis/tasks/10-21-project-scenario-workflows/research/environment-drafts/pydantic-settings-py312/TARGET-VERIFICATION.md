# Research: Pydantic Settings 离线环境与目标镜像验证

- Query: 固定完整依赖能否在目标账号镜像离线安装，并完成原版与参考 Union 修复的业务／完整原生回归？
- Scope: internal；只创建本研究命名容器，参考补丁仅用于容器临时副本，未调用模型或修改正式产品。
- Date: 2026-10-21

## Findings

已准备 64 个固定版本 wheel，共 58,386,309 字节。`profile/profile.json` 按当前 `validate_environment()` 结构填写，逐制品真实 SHA256 位于 artifacts 清单；完整安装清单在 `profile/requirements.txt`，没有改用最新版或在线补依赖。

目标镜像为 `vibebench-v3-account:v3-project-repairs-local-20261021-e`，ID 为 `sha256:d055c5f0035c8fb3f204ed97d6f774a38afdb3515f5503f7fa028adb6a5e908d`，linux/amd64。实际 Python 3.12.15，解释器为 `/opt/mitm/bin/python3`；每次用离线 wheel 安装至临时 `/work/dependencies`，候选库从 `/work/project/library` 导入。

容器均为 network none、UID/GID 1000、只读根、cap_drop ALL、no-new-privileges、内存及内存＋swap 均 1,024 MiB、pids 128。工作 tmpfs 为 1,536 MiB 上限并显式启用 exec，临时 tmpfs 为 256 MiB；实际用量仍受 cgroup 1,024 MiB 总内存限制。

| 实跑对象 | 完整原生集合 | 命令墙钟 | 独立 Union 观测 | 容器整体内存峰值 | PID 峰值 |
| --- | --- | --- | --- | --- | --- |
| 固定原版 | 1,256 通过、5 普通跳过、0 失败／错误 | 13.104 秒 | 0.469 秒，原始嵌套值为字符串，整体 JSON 对象绕行有效 | 568,463,360 字节 | 27 |
| 仅研究副本应用参考补丁 | 1,256 通过、5 普通跳过、0 失败／错误 | 11.498 秒 | 0.419 秒，全部冻结目标结果一致 | 565,690,368 字节 | 25 |

两轮测试命令均为 `/opt/mitm/bin/python3 -m pytest tests -q -ra --junitxml=/evidence/native-tests.xml`，在完整 `library` 根执行，未裁剪原生测试。5 个 skip 分别为 Windows 大小写条件 1 项、上游 CLI metavar 明示 skip 3 项及 PyYAML 已安装时的缺包用例 1 项；逐项见各轮 `native-summary.json`，没有因缺依赖新增跳过。

参考目标覆盖空列表、中文列表、普通文本、非法 JSON 字符串、多个键、非法列表元素、精确大小写，以及普通 Union／NoDecode／ForceDecode／enable_decoding 的已有顶层行为。原版观测与修复目标分开保存；参考补丁只改变研究副本的 `env.py`，原上游和草案 seed 的 58 个文件摘要复核不变。

离线安装命令墙钟分别为 10.629／9.817 秒。上表峰值读取 cgroup v2 `memory.peak`，覆盖安装＋测试＋业务整容器，不是单进程 RSS；原生子进程最大 RSS 分别为 335,380／335,972 KiB，单列在结果 JSON，不能相加冒充整容器峰值。

## 命令与证据

- 下载精确命令、耗时和退出码：`evidence/download-result.json`、`download.log`；64 个 wheel 的元数据和 SHA：`evidence/wheel-metadata.json`。
- 原版成功证据：`evidence/bench-scenario-research-ps-baseline-3e6a94fe/`。
- 参考副本成功证据：`evidence/bench-scenario-research-ps-reference-b2d086cb/`。
- 每轮均有 `create-command.json`、真实容器 ID／inspect 状态、完整安装／测试／业务日志、JUnit、计时、cgroup 峰值与删除结果。
- 汇总对账为 `evidence/target-verification.json`；当前档案静态验证为 `evidence/profile-validation.json`。
- 可复用运行入口：`python3 <本目录>/runner/control.py baseline` 与 `reference`。入口仅认领 `bench-scenario-research-ps-*` 精确容器，核对名称和所有者标签后删除，不操作已有账号环境。

## Caveats / Not Found

- 首轮未显式 exec 的 `/work` tmpfs 导致 black／pydantic_core 本地扩展映射失败，尚未进入有效原生测试；该失败完整保留在 `evidence/bench-scenario-research-ps-baseline-2b6c5ec7/`。显式 exec 后两轮成功，未增加容器特权，不能把首次环境失败记为候选 BUG。
- 验证范围是该镜像、该平台、固定完整依赖和列明原生／Union 套件。其他场景业务脚本、回答提取的真实模型质量、其他平台与生产部署仍未验证；不能把此处通过称为 7 个任务全部模型通过。
- 本轮共 3 个研究容器，全部已精确删除；无残留。未修改正式代码／规范、上游源码或运行中的账号环境，模型调用数为 0。
