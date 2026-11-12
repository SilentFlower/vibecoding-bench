# 真实项目审查：charset-normalizer

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[jawah/charset_normalizer](https://github.com/jawah/charset_normalizer)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[0a9201767e9d888b5a5ed7ca44400192474ad1b0](https://github.com/jawah/charset_normalizer/tree/0a9201767e9d888b5a5ed7ca44400192474ad1b0)。
- 许可证：MIT。读取LICENSE与项目元数据，保留TAHRI Ahmed R.版权、MIT许可与免责。README中对其他项目的陈述不作为本仓许可证结论；本仓按实际MIT文本记录。
- 用途：从本地字节/文件检测可读编码候选，给出chaos/coherence与语言信息，并输出归一化文字。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 100／595063 |
| 产品 Python 文件／行数 | 12／6312（src/charset_normalizer/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、2g 上限运行 |
| 安装 | 16.706 秒，venv 50125064 字节（含本轮测试依赖） |
| 原生基线 | 620 主测试通过、16 子测试通过；0 失败、0 错误、0 跳过（JUnit通过聚合636）；墙钟 12.772 秒，exit 0 |
| 测试峰值 RSS | 786368 KiB（容器测试进程观测） |

产品纯Python路径无必需运行依赖、服务或凭据。完整上游集合中TOO_BIG_SEQUENCE为10,000,000；test_misleading_large_sequence构造约180MB ASCII加中文尾段，导致测试峰值786,368KiB（约768MiB），最终用2GiB容器上限通过，不能称为512MiB全套可跑。普通读取/转码业务另在256MiB上限容器运行成功；本轮未单独取该业务峰值RSS。

完整默认pytest集合。首次取证夹具未加入临时src路径导致收集错误，已保留fixture-first-*；随后512MiB运行在上游180MB大样本测试触发OOM，保留oom-512m-*并去除了未生成新JUnit时误读的旧计数。最终2GiB上限完整重跑620主测试及16子测试通过，未删选大样本测试。未执行nox的Cython编译矩阵、外部char-dataset性能/兼容批次、覆盖率门槛和文档构建。

## 源码与真实场景

读取from_bytes的codec优先级、声明/BOM处理、分段chaos与coherence、提前结束及fallback，from_fp/path整份读取合同，CharsetMatch的原始字节/延迟str/输出缓存及等价候选组。API实际实现src布局，产品不是替换成简化检测器。已有CLI JSON、多文件、候选替代、声明头更新、binary判断和alias列表不作为新能力重复计数。路线分开处理流读取、输出编码、歧义决策和归档保存等完整交付，均为增强提案，字节所有权等兼容选择明确保留。

独立256MiB离线场景读取UTF8 BOM中文和带windows-1252声明的法文，API与真实from_path读盘结果一致；将output写到/tmp实际文件后按UTF8重读保留中文/François，原编码声明由已有逻辑更新。观察脚本还记录from_fp.read(-1)、中文转ASCII默认??以及bytearray外部修改后raw/缓存text不一致的实际现状；后两者是新增策略的依据，不伪称已改变默认。加载/source/src/charset_normalizer/__init__.py。

完整 [20 步路线](./charset-normalizer-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/charset-normalizer/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/charset-normalizer/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/jawah/charset_normalizer.git <checkout>
git -C <checkout> checkout --detach 0a9201767e9d888b5a5ed7ca44400192474ad1b0
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

完整基线命令`<含docker SDK的Python> <evidence>/run_native.py baseline <evidence> --memory 2g`；普通业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。原生测试在容器tmp副本写测试文件，产品检出保持只读。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
