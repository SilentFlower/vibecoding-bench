# 真实项目审查：path（path.py）

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作独立冻结验收或接入正式库。

## 来源与固定版本

- 官方仓库：[jaraco/path](https://github.com/jaraco/path)。
- 固定提交：[b5ae11e41ba64a9e27fdc42d8c138d7db7699910](https://github.com/jaraco/path/tree/b5ae11e41ba64a9e27fdc42d8c138d7db7699910)，版本 固定提交源码；浅检出 SCM 安装版本 0.1.dev1+gb5ae11e41（不当作官方发行版）。
- 许可证：MIT。pyproject.toml 明确 MIT，构建插件 coherent.licensed 动态生成 LICENSE（已单独保存 build-generated-LICENSE.txt），源跟踪文件中没有独立 LICENSE；保留分发生成的许可原文及原仓归属，不能把占位版权行自行补成新声明。
- 继承 str 的路径／文件操作库，提供遍历、读写、哈希、复制、合并、权限和临时目录上下文；无外部服务，核心可在 Python -S 下导入。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 32／159827 |
| 产品 Python 模块／行数 | 4／2312（path/） |
| 环境 | Python 3.12.3、Linux，独立 venv 和临时检出，隔离 HOME，不挂账号或真实配置 |
| 安装 | 17.33 秒，venv 52571970 字节；包含测试工具，网络和缓存影响耗时 |
| 原生基线 | 142 通过、0 失败、0 错误、1 跳过、0 预期失败；墙钟 5.50 秒 |
| 子进程峰值 RSS | 77088 KiB；本轮安装与测试子进程共享累计观测的最大值，不能当作精确单包常驻内存 |

核心依赖为空，Python ≥ 3.10；Path.special 可选依赖 appdirs。本轮安装 test extra 与 pytest-enabler，冻结依赖包含 appdirs、more_itertools、packaging 等；没有安装 check/type/doc extra 或运行 Windows。

142 通过、1 跳过；唯一跳过为 Windows-only Path.startfile。pytest.ini 默认收集的模块 doctest 已包含在 142 项内，不另外混加。安装日志保存构建用 setuptools／setuptools_scm／coherent.licensed。

Path 是 str 子类，_next_class 保留派生路径类型；iterdir→walk 的深度优先生成器允许 send 控制单个目录进入，walkfiles／walkdirs 筛类型。glob 明确非递归，copytree 直接代理 shutil，merge_tree 在已有目录上覆盖并递归。in_place 先把旧文件改为 .bak 再创建新目标；SpecialResolver 使用可选 appdirs。已读真实方法和测试，不把已有 ignore、copy_function、dirs_exist_ok、with_stem、group、hardlink_to、read_bytes／write_bytes 等再次算新功能。

## 原生使用场景和改进研究

实际 Unicode 文件 copy2 后读回，SHA-256 与固定源码导入路径已核对。复现 #263：symlinks=True 的第二次 merge_tree 抛 FileExistsError；复现 in_place：受控 KeyboardInterrupt 后原内容丢失、备份已被删（发生在合成临时文件）。受控取 walk 的前 12 项后显式 close，观察到符号链接循环持续递归；没有启动无限遍历。公开签名确认 walk 无深度／排序策略、hash 无 usedforsecurity、touch 无 exist_ok、write_lines 无换行选项；resolve／relative_to／iter_lines／rglob 等缺少。源码已有 merge_tree(ignore=...)，已排除不计步。

完整 [20 步路线](./path-roadmap-20.md)逐步给出来源、现状、模块、兼容和正反验收。增强是本试点的工程提案，开放 issue 只提供需求线索，不代表上游承诺或已接受。测试、文档和失败重试不拆步。

## 重跑与证据

证据目录：`.deploy/github-100-research/cli-config/path/`；固定源码当前位置 `/tmp/github-research-path-tpvfua11/source`，可删除重建，不在产品快照内。

```bash
git clone https://github.com/jaraco/path.git <checkout>
git -C <checkout> checkout --detach b5ae11e41ba64a9e27fdc42d8c138d7db7699910
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e '<checkout>[test]'
```

在无业务祖先配置的 checkout 目录运行 `<venv>/bin/python -m pytest -q -ra`；PATH 前置 venv/bin，HOME 指向独立空目录。原版场景执行 `<venv>/bin/python <evidence>/observe.py`。

- `repository.json`、`issues.json`、`revision.txt`：官方元数据、需求原文和冻结提交；构建生成的MIT许可保留在 `build-generated-LICENSE.txt`，原源码作者归属一并保存。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：依赖与成本。
- `baseline-tests.log`／`baseline-tests.xml`／`baseline-result.json`：原生执行结果、跳过和真实命令。
- `observe.py`／`observations-result.json`：原版场景、接口缺口与已存在能力对照。
- `roadmap-20.json`／`review-result.json`／`evidence-sha256.json`：路线、完成状态和证据摘要。

未在账号镜像、Windows、FIPS 系统或跨设备文件系统执行；FIPS 为明确待验的增强场景，未称复现 FIPS 错误。路线中的镜像删除、校验文件和同步计划均未实施，未对仓库或生产目录执行任何删除同步。

现有平台 verifier 仍限定 app.py JSON 行协议，本研究没有绕过它接入。后续须冻结独立验收、确认实际加载候选源码、离线预备依赖并累计回归。未修改上游源码、正式项目库、账号配置或生产数据，未提交／推送／部署，未向上游发消息；平台评测模型调用为 0。
