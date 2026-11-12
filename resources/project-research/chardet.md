# 真实项目审查：chardet（历史稳定5.2.0）

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[chardet/chardet](https://github.com/chardet/chardet)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[fa905b359cbcaba93a35fd6429ba9ec4b156c1c1](https://github.com/chardet/chardet/tree/fa905b359cbcaba93a35fd6429ba9ec4b156c1c1)。
- 许可证：LGPL-2.1-or-later（固定5.2.0）。固定5.2.0的LICENSE为LGPL2.1，源码头明确2.1或更新版本；保留原版权、许可、修改说明及适用源码/再链接权利。后续重写分支pyproject声明0BSD，选版不据此推断争议结论；未将两个版本或旧fork计作两仓。
- 用途：历史稳定版通用字符编码检测，提供单次/全部候选API、可复用增量检测器和本地文件CLI。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 505／8183485 |
| 产品 Python 文件／行数 | 49／41288（chardet/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 9.602 秒，venv 50169000 字节（含本轮测试依赖） |
| 原生基线 | 754 主测试通过、0 失败、0 错误、0 普通跳过、10 预期失败；墙钟 31.521 秒，exit 0 |
| 测试峰值 RSS | 98852 KiB（容器测试进程观测） |

5.2产品无必需第三方运行依赖，本轮只装pytest。主安装9.602秒，完整基线512MiB上限，墙钟31.521秒，RSS98,852KiB。后续分支曾下载83.85MB独立测试数据并在512MiB OOM，这些是另一个未完成版本的取证成本，不是5.2运行要求或通过证据。

完整5.2默认pytest集合764项：754通过，10条ISO-8859-9/Turkish legacy重命名用例为上游xfail，普通skip0；另2条pytest参数生成器弃用警告。未删选；包含tag内真实测试语料，无需后续分支外部test-data库。未跑其他Python、性能基准、发布构建或后续重写分支完整集合；后者的OOM记录保留但不混入本版结果。

## 源码与真实场景

选择真实tag5.2.0及完整commit作为已核对许可和原生基线的研究对象。初始后续分支88107b4ab8abc8b202fd145bc457b8b481557c87现场保留在source-v7/v7-candidate，本报告不计其未完成的基线。读取5.2 detect/detect_all、UniversalDetector的BOM/状态/prober/close/reset及CLI。read-only观察另外以AST读取后续分支真实detect参数和CLI旗标：已存在compat_names、编码允许排除、max_bytes、空/无结果政策及mime_type；路线03—07明确是冻结5.2的兼容升级方案，绝不称当前上游尚未提供。这些后续实现未在本轮复制或移植。其他缺口均只针对冻结5.2，不推断后续全版本状态。

普通256MiB离线场景检测并解码UTF8中文文件，以7字节分块feed后文字逐字一致；另检查UTF16 BOM输入及detect_all候选。原版缺陷证据是同一UTF8 BOM输入整份与1字节分块得到不同标签；特殊UCS4返回标签被正确识别但Python没有同名codec，作为详情增强依据。加载/source/chardet/__init__.py且__version__为5.2.0。

完整 [20 步路线](./chardet-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/chardet/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/chardet/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/chardet/chardet.git <checkout>
git -C <checkout> checkout --detach fa905b359cbcaba93a35fd6429ba9ec4b156c1c1
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

重跑需显式checkout完整fa905b359cbcaba93a35fd6429ba9ec4b156c1c1（tag5.2.0），不能直接使用默认后续分支。完整基线`<含docker SDK的Python> <evidence>/run_native.py baseline <evidence> --memory 512m`；业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。本轮observe附带读取已保存后续分支AST以核对既有能力；跨机器复核该部分另检出88107b4ab8abc8b202fd145bc457b8b481557c87到source-v7，仅作只读比较。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
