# 真实项目审查：ftfy

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[rspeer/python-ftfy](https://github.com/rspeer/python-ftfy)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[74dd0452b48286a3770013b3a02755313bd5575e](https://github.com/rspeer/python-ftfy/tree/74dd0452b48286a3770013b3a02755313bd5575e)。
- 许可证：Apache-2.0。LICENSE.txt明确Copyright 2023 Robyn Speer并指向Apache2.0；README特别要求准确作者归属。未来复制/分发保留版权、许可证及所需声明，修改版注明变更。
- 用途：对已经解码的Unicode文本修正mojibake、字符宽度、连字、换行与可选标点，并解释可重放的修整步骤。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 56／627550 |
| 产品 Python 文件／行数 | 9／3244（ftfy/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 18.358 秒，venv 50519122 字节（含本轮测试依赖） |
| 原生基线 | 358 通过、0 失败、0 错误、10 预期失败；墙钟 3.296 秒，exit 0 |
| 测试峰值 RSS | 36292 KiB（容器测试进程观测） |

运行依赖只有wcwidth，无外部服务。固定上游uv.lock规定的wcwidth0.2.13，安装调整见install-lock.json/log，最终requirements-frozen.txt为准；首次18.358秒为主安装阶段，锁定版本调整独立保留但未取得额外墙钟，不伪报总安装耗时。完整原生基线峰值约35MiB。

完整默认pytest集合含产品模块doctest及tests；10项是上游known-failures.json对应xfail，不是未运行项目。首次最新wcwidth0.9.3改变soft-hyphen宽度导致一个doctest失败，已按固定源码uv.lock恢复0.2.13；首次CLI临时启动器不可执行也已修正为只读挂载原生console-script。所有原始失败日志保存在fixture-first-*，最终完整集合0失败。未跑Ruff、mypy、Sphinx或其他Python矩阵。

## 源码与真实场景

读取TextFixerConfig的实际字段与默认值，ExplanationStep/ExplainedText数据结构，fix_text分段、fix_and_explain反复收敛、编码启发式和fix_file的解码/按行顺序，以及CLI的文件读写合同。核心仅支持已解码Unicode修整，guess_bytes明示不是通用编码检测器。已存在的实体解码、宽度修整、解释重放、Unicode说明和文件生成器不重复当新功能。第01步定位到解释关闭分支漏传config，第02步是零分段长度不能前进，第03步是按字节分行先于UTF16解码；三者均有固定提交实跑证据。其余为明确增强。

实跑混合法文mojibake、HTML实体、中文、CRLF、全角英文及fi连字，得到Français & 中文换行Hello file；ExplanationStep用apply_plan重放与结果完全相同。fix_file逐行修复café并保留正常中文；monospaced_width(中文A)为5。observe.py另保存三个固定提交缺陷及17个公开能力缺口。加载/source/ftfy/__init__.py，业务exit0。

完整 [20 步路线](./ftfy-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/ftfy/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/ftfy/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/rspeer/python-ftfy.git <checkout>
git -C <checkout> checkout --detach 74dd0452b48286a3770013b3a02755313bd5575e
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

用固定wcwidth0.2.13准备依赖。完整基线命令`<含docker SDK的Python> <evidence>/run_native.py baseline <evidence> --memory 512m`；业务`<同一Python> <evidence>/run_python_probe.py <evidence>`。native-bin/ftfy为pyproject声明ftfy.cli:main的等价启动器，直接调用原函数；宿主绝对venv shebang不适用于容器，因此单独只读挂载。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
