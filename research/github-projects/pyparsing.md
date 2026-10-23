# 真实项目审查：pyparsing

研究日期：2026-10-21。来源、适用原生基线和二十步路线已研究；尚未实施路线、制作冻结独立验收或接入正式库。

## 来源与固定版本

- 官方仓库：[pyparsing/pyparsing](https://github.com/pyparsing/pyparsing)；官方公开仓库页面、源码项目URL与真实Git提交对象已交叉核对，原始内容见repository.json、commit.json和official-repository.html；匿名API限流时未伪造API结果。
- 完整提交：[810199f89bf916590426e1c5cb3d612584f11a2f](https://github.com/pyparsing/pyparsing/tree/810199f89bf916590426e1c5cb3d612584f11a2f)。
- 许可证：MIT。LICENSE保留Paul McGuire版权、MIT许可和免责；官方README、pyproject URLs与真实Git提交交叉核对。
- 用途：用Python组合子声明文本语法，执行完整解析、扫描、语义转换并返回ParseResults。

## 实测规模与运行成本

| 项目 | 实测 |
| --- | --- |
| 跟踪文件／总字节 | 293／13458653 |
| 产品 Python 文件／行数 | 17／13001（pyparsing/） |
| 环境 | Linux；宿主安装Python 3.12.3、独立venv；账号镜像执行Python 3.12.15；原生测试在账号镜像 UID 1000、只读根文件系统、无网络、512m 上限运行 |
| 安装 | 15.553 秒，venv 213343176 字节（含本轮测试依赖） |
| 原生基线 | 2,175 主测试通过、2,089 子测试通过；0 失败、0 错误、0 跳过（JUnit通过聚合4,264）；墙钟 143.819 秒，exit 0 |
| 测试峰值 RSS | 409900 KiB（容器测试进程观测） |

核心语法库无必需运行依赖；本轮原生unit额外安装railroad-diagrams/Jinja2及matplotlib，后者依赖NumPy/Pillow等，安装日志与最终冻结清单单列。完整unit墙钟143.819秒、峰值409,900KiB（约400MiB），512MiB内完成；不是毫秒级小测试。另普通业务观察在256MiB预算完成。

完整执行上游tox unit范围 tests examples/tiny/tests，包含配置的diagrams额外依赖与Python3.12适用matplotlib；未删选用例。Sphinx doctest是独立tox环境，未执行，不能把unit通过叫全部文档通过；mypy与其他Python解释器矩阵也未验证。

## 源码与真实场景

读取ParserElement.parse_string/scan_string/parse_file、类级packrat与左递归开关、语义动作适配、Located、ParseResults.as_dict以及ParseBaseException坐标/解释结构。已有字节文件解码、debug回调、铁路图、数值表达式、ignore、original_text_for及EBNF示例均标明替代方式，不冒充未存在。路线面向复杂配置语法的独立完整交付，均为增强提案；高级增量、异步和候选枚举明确限制纯动作、预算与支持组合子，不宣称已经实现。

真实解析本地资源清单books=3;reports=5，经命名词元和integer语义转换得到两个结构化记录并汇总8；错误books=no产生ParseException并保留实际loc/line/column；中文说明中scan_string找到3和5及原文区间。确认加载/source/pyparsing/__init__.py，20个新增公开入口检查均记录。

完整 [20 步路线](./pyparsing-roadmap-20.md) 含逐项来源／实际场景、原版缺口、交付、模块、兼容、正常及异常验收和真实依赖。新增 API 均为研究提案，不声称这些目标已通过验收。

## 重跑与证据

证据目录：`.deploy/github-100-research/resume-text/pyparsing/`；固定源码：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-text/pyparsing/source`。原生安装命令和依赖见 install.log、installation-result.json、installation.json、requirements-frozen.txt。

```bash
git clone https://github.com/pyparsing/pyparsing.git <checkout>
git -C <checkout> checkout --detach 810199f89bf916590426e1c5cb3d612584f11a2f
python3 -m venv <venv>
<venv>/bin/python -m pip install -r <evidence>/test-requirements.txt -e <checkout>
```

依赖按requirements-frozen/test-requirements准备。完整unit命令`<含docker SDK的Python> <evidence>/run_native.py baseline <evidence> --memory 512m --tests tests examples/tiny/tests`；业务`<同一Python> <evidence>/run_python_probe.py <evidence> --memory 256m`。运行时将固定源拷到容器tmp以满足原生写入测试，不改原检出。

- `revision.txt`、`repository.json`、`commit.json`：来源与固定提交。
- `source-analysis.json`、`size.json`、`installation*.json`、`install*.log`、`requirements-frozen.txt`：真实源码与依赖成本。
- `baseline-tests.log`、`baseline-tests.xml`、`baseline-result.json`：上游原生测试、退出码和资源。
- `observe.py`、`observations-result.json`：真实原版使用场景及接口观察。
- `roadmap-20.json`、`review-result.json`、`evidence-sha256.json`：结构化路线、状态及证据摘要。

未修改正式项目库、产品源码、账号配置或生产数据；未执行上游消息、提交、推送或部署。研究完成与平台接入、模型完成和生产发布分别统计；现有 app.py verifier 尚需原生适配。
