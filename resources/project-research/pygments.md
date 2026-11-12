# 候选审查：Pygments（暂不计入研究完成）

研究日期：2026-10-21。官方 [pygments/pygments](https://github.com/pygments/pygments)，固定 [156d85fdd18d34427fe893527e71da91dcfb0eb5](https://github.com/pygments/pygments/tree/156d85fdd18d34427fe893527e71da91dcfb0eb5)，版本2.21.0。已检出、读相关源码、跑完整适用原生基线和真实CLI；**因整仓测试样本许可尚未核清，保持候选，不计入100项目完成数**。本仓也有128,213行产品源码，维护规模大于首批轻量示例。

## 已核实的工程与成本

- 核心为纯Python语法高亮：lexers生成token流，filters调整token，formatters生成HTML/终端/LaTeX等；真实API为lex/format/highlight，CLI为pygmentize或python -m pygments。
- 固定工作树2796个文件、45,269,203字节；pygments/产品Python源码343文件、128,213行。
- 必需运行依赖为0；本轮安装上游tox测试对应pytest~=8.2、pytest-cov、pytest-randomly、wcag-contrast-ratio。安装21.91秒，专属venv 27,620,778字节；精确实际依赖在requirements-frozen.txt。未跑tox包装层、多Python、regexlint/pylint/ruff或Sphinx。
- 账号镜像`ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像ID`sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`；UID/GID1000，无网络/凭据，源码和依赖只读、根只读、删除capabilities、禁止提权，512MiB内存且无额外swap，PID128，tmpfs256MiB；源码复制到临时目录后运行。未验证产品默认256MiB/PID64预算。
- 完整原生基线5330通过、0失败/错误、16跳过；测试进程26.44秒，峰值RSS 190,632KiB。跳过：8项缺Pillow、1项缺latex、4项上游SRCINFO文件名限制、3项上游guess分类差异。并未把这些跳过算成产品缺陷。
- 原生CLI将含中文的Python代码文件高亮到临时HTML，重新读取确认span和代码内容，临时目录自动清理。
- 20条观察保留在reproductions-result.json，含TNT无结尾换行卡住、Hare二进制/标识符、ANSI黄色、Markdown MIME、Batch展开、INI引号、C多字符常量、VHDL/RPM/Docker缺口、LESS嵌套import、Cypher、Make、diff内嵌语法和新增lexer等线索。TNT复现由0.5秒外部超时杀死回收。**这些是路线候选，尚未完成正式20步边界审查，不记为20项已完成路线**。部分已有能力不能据旧issue重复计数。

## 许可准入原因

主LICENSE是BSD-2-Clause，AUTHORS与版权条件需保留。整仓的tests/examplefiles包含不同归属，不能仅按主许可证统一打包：

- [Delphi example.pas](https://github.com/pygments/pygments/blob/156d85fdd18d34427fe893527e71da91dcfb0eb5/tests/examplefiles/delphi/example.pas)明示GPL。
- [Modelica Constants.mo](https://github.com/pygments/pygments/blob/156d85fdd18d34427fe893527e71da91dcfb0eb5/tests/examplefiles/modelica/Constants.mo)指向Modelica许可，但当前片段没有附完整条件。
- [make/firefox.mak](https://github.com/pygments/pygments/blob/156d85fdd18d34427fe893527e71da91dcfb0eb5/tests/examplefiles/make/firefox.mak)带MPL1.1/GPL2/LGPL2.1声明。
- [modula2/Sorting.mod](https://github.com/pygments/pygments/blob/156d85fdd18d34427fe893527e71da91dcfb0eb5/tests/examplefiles/modula2/Sorting.mod)明示“it may not be sold”。

[上游#2872](https://github.com/pygments/pygments/issues/2872)记录相同整仓样本归属疑问；以上结论来自实际冻结文件内容，而非只引用issue。这里不作统一许可证兼容性保证。接入前需逐文件核对复用范围、补齐必要许可和归属；也可另行评审把有明确复用条件的真实产品源码作为seed、测试样本留在有独立授权的冻结验收范围。不能偷偷删除原生测试后仍宣称原工程全套可交付。

本轮不为凑100而强行计数；建议优先继续更小、归属明确的独立仓库，Pygments以后作为扩展候选。

## 证据与重跑

证据根`.deploy/github-100-research/text-formats/pygments/`，source与venv独立保存，未纳入Git或项目快照。repository.json/revision.txt/size.json、open-issues.json、installation-result.json/requirements-frozen.txt、baseline-output/tests.xml/process.log、baseline-result.json、reproduce.py/reproductions-result.json、observations-result.json与review-result.json均已保存。两次临时容器均删除、核对不存在，无OOM。

```bash
git clone https://github.com/pygments/pygments.git <checkout>
git -C <checkout> checkout --detach 156d85fdd18d34427fe893527e71da91dcfb0eb5
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> 'pytest~=8.2' pytest-cov pytest-randomly wcag-contrast-ratio
```

在预备依赖的无网络账号镜像内，源码复制到/tmp/source，执行：

```bash
python3 -m pytest tests -q -ra -p no:cacheprovider --randomly-seed=20261021 --junitxml=/results/tests.xml
python3 /evidence/reproduce.py
```

未实施路线、冻结增强验收或接入；未修改上游、产品、正式库、生产或其他人的改动；未提交/推送/部署，未向上游发消息，也未执行平台模型评测。
