# 真实项目审查：PyYAML

研究日期：2026-10-21。来源、适用原生基线和 20 步研究路线已完成；尚未实现路线、冻结新增验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[yaml/pyyaml](https://github.com/yaml/pyyaml)。YAML 1.1解析、节点组合、Python对象构造与YAML转储工具，提供纯Python与可选LibYAML实现。
- 固定提交：[f5e4504a92f169f65350a1047dccb23bc97028be](https://github.com/yaml/pyyaml/tree/f5e4504a92f169f65350a1047dccb23bc97028be)；版本与运行要求：7.0.0.dev0，Python>=3.8；固定为开发提交而非冒称稳定7.0已发版。
- 许可证：MIT。实际LICENSE保留Ingy döt Net、Kirill Simonov署名；setup.py Source Code与官方仓库一致。
- 来源确认采用官方 GitHub 仓库、REST 元数据、实际 LICENSE 与源码；issue 仅是线索，未复现项不称为缺陷。

## 实测规模与运行成本

| 项目 | 结果 |
| --- | --- |
| 跟踪文件 | 642 个，618,117 字节 |
| Python 产品源码 | 17 个文件、5,893 行 |
| Python 测试文件 | 25 个、2,572 行 |
| 隔离依赖安装 | 11.266 秒，venv 50,131,496 字节 |
| 适用原生基线 | 1287 通过、0 失败、0 错误、0 跳过 |
| 基线进程 | 4.408 秒，峰值子进程 RSS 42492 KiB |
| 容器运行 | 整体 4.889 秒，内存 256 MiB、PID 64，无 OOM |

纯Python运行无第三方依赖；可选LibYAML需C头文件/链接库及Cython构建。宿主无yaml.h，本次editable构建为纯Python，yaml.__with_libyaml__实测False；不下载或修改系统库来掩盖该限制。测试pytest，构建隔离的Cython等详见installation.json。

安装是单独依赖准备阶段；执行环境使用正式 V3 账号镜像 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`（镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`），Python 3.12、UID/GID 1000、无网络、只读根、移除 capabilities、禁止提权。只挂本仓源码、依赖、取证脚本和专用结果目录；源码复制到临时文件系统，HOME 为新建临时目录，未挂账号／父目录／宿主凭据或 Docker socket。基线与 smoke 容器均已删除并核对不存在。依赖锁定见 requirements-frozen.txt；预备环境不会混入源码快照。

## 原生结构与实际场景

Reader→Scanner→Parser产事件，Composer产带mark的Scalar/Sequence/Mapping Node图，Constructor结合Resolver生成Python值；Dumper逆向结合Representer/Serializer/Emitter输出。Loader/SafeLoader/FullLoader由这些mixin组成，SafeLoader限制标签但保留别名图。已读上述节点/loader、构造/合并/解析器注册、composer图关系和序列化等相关契约。

两文档服务配置用锚点合并默认端口，safe_load_all后真实写config.yaml并再次safe_load_all等值，另独立标准json文件读回。复现长键merge序列后项错误覆盖首项及四类无效显式tag泄漏原生异常两项根因问题；tuple键safe_dump后不能safe_load列为明确增强政策。YAML1.1 on/off转换、重复键后值胜出、compose已有源码mark均作原能力对照。

## 基线范围与限制

上游tox默认pytest集合1287通过、0失败/错误、0已收集跳过、1警告，覆盖新的merge/dump-load测试与legacy collector按fixture产生的用例。LibYAML扩展不存在时，官方collector直接不收集test_yaml_ext.py，因此0 skipped不代表C路径测试通过；本轮适用基线仅纯Python。

未构建/测试LibYAML C路径、其他解释器或打包矩阵。LibYAML不收集警告原样保留，不能把当前结果声称全实现合规。新loader配置若将来支持C实现必须额外冻结C/纯Python差分验收；本轮只提供源码研究，不修复上游、默认schema或业务平台。

## 迭代路线

[20 步路线](./pyyaml-roadmap-20.md)逐项包含原版缺口、交付、兼容边界、正常／异常验收、真实模块与回归入口；需求来自下述固定源码与实际使用场景，不声称上游已经采纳。缺陷复现／对照及公开 API 观察保存在 smoke-output/log.txt。

2项已复现问题修复+18增强；复合键读回作为新增政策而非擅自强制改变默认YAML图语义。已有safe_load_all惰性、compose marks、BaseLoader全字符串、自定义constructor/resolver、canonical标记和宽度/indent不重复计新功能；新特性不以Python/C两种实现各拆一步。

## 重跑与证据

证据根：`.deploy/github-100-research/data-tools/pyyaml/`（本地忽略目录，未纳入 Git；跨机器需重新检出、安装）。

```bash
git clone https://github.com/yaml/pyyaml.git <checkout>
git -C <checkout> checkout --detach f5e4504a92f169f65350a1047dccb23bc97028be
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

在无账号且无祖先配置的隔离环境执行原生命令：

```text
/usr/local/bin/python3 -m pytest -q -ra -p no:cacheprovider --junitxml=/output/baseline-tests.xml
/usr/local/bin/python3 /smoke.py
```

本轮容器可复跑入口：`.deploy/github-100-research/data-tools/research_runner.py`，例如以装有 Docker SDK 的 Python 执行 `research_runner.py --name baseline run pyyaml -- <上述原生命令>`；runner 只读挂载 `.deploy/github-100-research/data-tools/pyyaml/source`、本仓 site-packages 与 smoke.py，`/output` 是本仓专用结果目录。runner须加--pythonpath /lib，使导入来自/tmp/source/lib；缺LibYAML是当前环境已披露边界，不可额外安装PyPI稳定版替换固定源码。

- `repository.json`、`issues-open.json`、`revision.txt`、`size.json`：官方元数据、提交与逐文件规模。
- `installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`、`test-requirements.txt`：实际安装和固定依赖。
- `baseline-result.json`、`baseline-output/baseline-tests.xml`、`baseline-output/log.txt`：实际基线和计数。
- `smoke.py`、`smoke-result.json`、`smoke-output/log.txt`：原生业务副作用、原版能力观察。
- `research.json`、`roadmap-20.json`、`evidence-sha256.json`、`review-result.json`：逐仓研究、结构化路线和校验摘要。

本轮只形成研究文档。未修改上游源码、业务实现、正式库或线上数据；未提交、推送、部署或向上游发消息。模型执行、平台独立验收与生产接入均未开始。
