# 真实 GitHub 项目审查：Rich

研究日期：2026-10-21。适合无服务的终端文本工程迭代，运行成本可控；38,515行源码涉及多种组件，属于源码较多的轻量运行项目。 已完成固定源码、适用原生基线、真实使用场景和 [20 步路线](./rich-roadmap-20.md)；尚未实施路线、冻结改进后的验收或接入正式项目库。

## 来源与固定版本

- 官方仓库：[Textualize/rich](https://github.com/Textualize/rich)，元数据归档状态为 false。
- 完整固定提交：[9d8f9a372cc5916fd4781fec207ced7ddac2f08f](https://github.com/Textualize/rich/tree/9d8f9a372cc5916fd4781fec207ced7ddac2f08f)，包版本 15.0.0。
- 许可证：MIT。保留LICENSE和源文件归属；未向上游提交issue/PR。AI_POLICY只在实际上游贡献时按其要求处理，本轮为本地只读研究。
- 官方说明与检出源码相互核对；研究所列增强是试点提案，不代表上游承诺或维护者接受。

## 原生工程与运行成本

Console把Text/Panel/Columns/Table等renderable转换为Segments后输出；Text维护plain/span样式并经cells/_wrap按终端格宽折行，AnsiDecoder解析ANSI文本。Console可记录后导出HTML/SVG/文本。Traceback提取异常链和帧，RichHandler接logging，Progress用Task维护时钟与进度，Prompt格式化选项并读输入。已读相关构造与字段、实际实现和测试；研究保留原始多模块工程。

| 项目 | 实测／核对结果 |
| --- | --- |
| 跟踪文件／字节 | 553／19749966 |
| 产品源码 | 38515 行 Python，100 个文件 |
| 环境 | 安装宿主 Python 3.12.3；隔离执行 Python 3.12.15／Linux |
| 依赖 | 产品必需Pygments和markdown-it-py（后者依赖mdurl）；本轮审查poetry.lock后固定其Pygments2.19.2、markdown-it-py3.0.0及pytest7.4.4/pytest-cov3.0.0/attrs21.4.0。其他传递依赖以requirements-frozen.txt实际版本为准，并非整份poetry.lock都安装 |
| 外部系统 | 不需要外部服务或凭据；未装Jupyter/ipywidgets，不启动真实终端交互/浏览器或网络链接 |
| 安装耗时 | 24.05 秒；受缓存与网络影响 |
| 独立 venv 大小 | 30,916,011 字节，含 pip 和本轮测试工具 |
| 原生基线 | 956 通过、0 失败、0 错误、25 跳过 |
| 测试进程墙钟／峰值 RSS | 8.11 秒／75,232 KiB |

完整pytest tests原生基线956通过、25跳过、0失败/错误；25项原因为17项windows only、2项Windows specific、5项py3.12渲染差异、1项Python3.11之后不适用。仅Linux/Python3.12，未跑Windows/macOS/Jupyter、lint/mypy/docs、coverage上报、benchmark或tox/poetry包装层。安装先有默认依赖，再按已读锁文件固定基线版本，总安装时间为两阶段之和，initial-*保留第一阶段。未运行Pygments2.21兼容矩阵，不将open issue #4209直接当本轮复现。

## 隔离验证与真实使用

原生基线与观察均使用 `ghcr.io/silentflower/vibebench-v3-account:v3-ci-39482854683-1`，镜像 ID `sha256:72d65643b550824e2422090c7d152d954e35ddf6247e80b8ae5d30855a2750dc`。UID/GID 1000、无网络、只读根、cap_drop=ALL、no-new-privileges、内存 512m／无额外 swap、PID 上限 128；源码和预备依赖只读挂载后复制源码到容器临时目录。未挂账号 HOME、认证文件、业务环境或 Docker socket。独立输出目录保存 XML 和日志；本仓各次临时容器均已删除并核对不存在，无 OOM。

实际创建中文Table并通过record=True的Console渲染，save_html落盘并重新读取核对表格内容及span；原生对象20项观察全部执行。循环异常链由0.5秒子进程超时回收，其余输入均在内存流或专属临时目录；ANSI控制字符只保存为JSON/转义表示，不发送到真实终端。

18项修复均有当前原版证据：ZWJ格宽越界、异常链循环、负索引样式丢失、非正格宽不一致、ANSI里NUL使ESC残留、空关键字产生零长span、ParseError二次异常、Text自身justify被覆盖、SVG最后行悬空clipPath、Columns窄宽度除零、save_text失败丢记录、cwd权限导致import失败、NBSP断行、异常notes串链、日志格式异常逃逸、ANSI CRLF丢正文、Progress停止后reset计时为负、日志时区丢失。whole-word高亮与Prompt选项分隔符为2项增强，明确不把现有substring设计统称缺陷。

保留既有颜色环境控制、Table/Panel/Markdown、markup、进度嵌套/Live、HTML/SVG/文本导出、自定义高亮与日志处理、Prompt子类化等能力。上游doc/test修正、删除sqrt、版本说明、未断言测试和旧issue本身不计用户功能。CJK ambiguous宽度需终端策略决定，未未经取舍直接改成2格；Jupyter/Windows报告未在本轮环境复现，不列已证实修复。SVG本轮只验证XML引用完整性，没有声称已进行跨浏览器字体/像素验收。

## 二十步路线与接入边界

20步为18项已复现修复和2项增强。非正格宽的几种症状合为一步；异常循环与notes归属是不同用户后果，分别交付。所有内容包含原生累计回归和独立验收，不把测试修补当独立业务步。

每步包含实现、测试、文档、当前能力与此前已接受能力回归；测试矩阵和重试不另计步。本轮只研究，不把原版缺口观察当作修复后验收。现有平台verifier仍只支持app.py/JSON行，未适配Rich的Console/API和文件结果。后续原生验收应导入候选包、固定离线依赖与Console宽度/时钟，观察文本/span/XML及真实文件副作用。512MiB/PID128完整基线不等于默认256MiB/PID64预算或实机终端可用已验证。

## 证据与重跑

证据根：`.deploy/github-100-research/text-formats/rich/`（本地忽略目录，跨机器须重新准备）。`source/` 保留完整固定工作树；`venv/` 为本仓专属依赖，均不进入候选源码快照。

```bash
git clone https://github.com/Textualize/rich.git <checkout>
git -C <checkout> checkout --detach 9d8f9a372cc5916fd4781fec207ced7ddac2f08f
python3 -m venv <venv>
<venv>/bin/python -m pip install <checkout> pytest==7.4.4 pytest-cov==3.0.0 attrs==21.4.0 typing-extensions pygments==2.19.2 markdown-it-py==3.0.0
```

本轮实际隔离执行命令：

```bash
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run rich baseline -- \
  -m pytest tests -q -ra -p no:cacheprovider --junitxml=/results/tests.xml
.deploy/project-iteration-repairs/venv/bin/python \
  .deploy/github-100-research/text-formats/research_tools.py run rich observations -- \
  /evidence/reproduce.py
```

- `repository.json`、`revision.txt`、`issues.json`、`source/`：官方来源、完整提交、需求线索与真实源码。
- `size.json`、`installation.json`、`installation-result.json`、`install.log`、`requirements-frozen.txt`：规模、安装和精确实际依赖版本；上游锁文件是否沿用见以上说明。
- `baseline-output/tests.xml`、`baseline-output/process.log`、`baseline-result.json`：完整适用测试输出、数量、资源与清理证明。
- `reproduce.py`、`observations-output/process.log`、`reproductions-result.json`、`observations-result.json`：真实入口、原版观察、对照和清理记录。
- `roadmap-20.json`、`profile.json`、`evidence-sha256.json`、`review-result.json`：逐项路线、审查结论、证据摘要和计数状态。

未修改上游源码、产品、正式库、生产或其他人的未提交文件；未向上游发送消息，未提交、推送、部署，也未执行平台模型评测。
