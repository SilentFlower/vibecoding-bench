# Hjson 候选审查：暂不计入百项目

官方仓库 [hjson/hjson-py](https://github.com/hjson/hjson-py)，固定提交 `9351a277df1a226fdceb00228fb5daae785447a8`；setup.py 为 3.1.0。实际 LICENSE.txt 为 MIT OR AFL-2.1，保留 Bob Ippolito 和 Christian Zangl 版权。跟踪文件 189 个、405665 字节；运行无第三方依赖。它是带注释、无引号字符串及多行字符串的 JSON 变体，实现从 simplejson 分支演进。

上游 setup.py test 调用 `hjson/tests/__init__.py` 的 `all_tests_suite()`，包含模块 doctest。本次在无网络、无账号挂载、只读根/源码、UID1000、256MiB/PID64 的 V3 Python3.12 容器调用同一套件：**107 通过、1 失败、0 错误/跳过**。失败为 hjson 模块 doctest 期待 `OrderedDict([...])` 而 Python3.12 实际 `OrderedDict({...})`。没有删除或跳过这个失败；完整 XML、日志与官方开放 issue #40 线索均保留。本原生套件本来就未包含 test_tool，test_hjson 也按上游逻辑略过 extra 与 stringify/quotes fixtures，不宣称全 Hjson 跨实现合规。

真实使用场景：带中文注释的服务配置解析、三引号多行内容、真实 `python -m hjson.tool -j` 输出 JSON 文件并独立 json 读回，均通过。源码读取覆盖 decoder 注释/字符串/容器扫描、HjsonEncoder 引号和多行编码、公开 load/dump 契约与 CLI。另在固定版本实际复现：未结束 `/*` 注释泄漏 IndexError；parse_float=Decimal 的 1.0 被改成 int；带 CR 的多行字符串经 dumps/loads 丢数据；bigint_as_string 在 Hjson 输出路径未生效，而 dumpsJSON 对照生效。旧 issue 的 URL 丢失未据标题认作 BUG。

本仓暂不纳入完成计数：目标 V3 原生基线仍有失败；此外与已收录 simplejson 的通用编解码核心高度重叠，未用同构功能补到 20 步。没有形成已完成路线，没有实施修复或平台接入。若未来专门恢复该候选，应先单独解决 Python3.12 原生基线并重新论证 Hjson 专属的 20 步，再独立复核。

证据根 `.deploy/github-100-research/data-tools/hjson/`：官方 repository/issues JSON、固定 source/revision、installation 锁与成本、baseline XML/日志、smoke.py/真实文件/日志、review-result.json。可复跑 `research_runner.py --name baseline run hjson -- /usr/local/bin/python3 /smoke.py --baseline` 和同入口 `/smoke.py`（不传 --baseline）业务场景；必须保持无账号隔离并只挂本仓依赖。smoke 初次取证脚本的 import 作用域错误已修正，原失败保留在 harness-preparation，不算产品缺陷。
