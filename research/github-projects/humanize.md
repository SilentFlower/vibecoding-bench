# Humanize：真实 GitHub 项目研究

来源、许可、固定源码、适用完整原生集合和本地业务场景已核对，形成[20项独立路线](./humanize-roadmap-20.md)。**仅研究，未实施路线，未冻结新增验收，未接入正式项目库。**

## 来源与规模

官方 [python-humanize/humanize](https://github.com/python-humanize/humanize)，固定完整commit `785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b`。主许可[LICENCE](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/LICENCE)为MIT，版权归Jason Moiron及Contributors，保留原声明。真实读取number/filesize/time/i18n/lists/__init__及关联原生测试与locale目录；不是按名称猜API。

跟踪89文件、404063字节；13个Python文件共3602行。宿主独立venv使用Python3.12.3，初始安装23.827秒，环境62041299字节。实际依赖与制品来源见requirements-frozen.txt/installation.json：pytest9.1.1、freezegun1.5.5、pytest-benchmark5.3.0、pytest-codspeed5.0.3、pytest-cov7.1.0等。运行库本身主要使用标准库；本次另需GNU gettext生成catalog并运行原生翻译检查。

GNU gettext0.21-14ubuntu2的3个deb共1045802字节，独立解包工具树3259623字节，没有向系统安装包。按上游scripts/generate-translation-binaries.sh生成36个ignored .mo，编译0.307秒，逐项SHA见translation-preparation.json。工具与生成资源成本独立于venv大小。未修改任何tracked源码。

## 实际原生基线与业务场景

完整上游默认收集（tox.ini中的doctest-modules保留），包含benchmark和翻译更新测试：**856主测试通过，0普通skip、0xfail、0xpass，退出0**；6.598秒，进程最大RSS98956KiB。这是在宿主Python3.12.3直接运行的独立venv结果，不冒称账号镜像Python3.12.15结果。原pytest日志、JUnit、命令、时间与环境保留。这里执行完整测试集合；未声称另外执行tox docs/lint/mypy任务或所有解释器矩阵。

第一轮缺少.mo和gettext工具导致744通过/112条件skip，原始log/XML/result/time已先归档pre-translation-assets，补齐本地翻译资源后再生成全新当轮JUnit，最终856全过；不得用旧XML覆盖新结果。翻译更新脚本没有产生tracked差异。

实际商品/工时显示场景：1536以binary显示1.5 KiB，7380秒精确显示2 hours and 3 minutes，fr_FR成功加载真实编译catalog。observe.py对20条路线逐条运行原版观察，结果保存observations-result.json；自定义翻译目录仅为临时合成one/uno/dos词条，没有外部服务或真实业务数据。

## 路线真实性

6项修复均有原版直接观察：超大有限整数被float误处理、intcomma指数表示、自定义容量文案进位报错、容量忽略区域小数点、最高SI桶有效数字进位、同locale不同catalog目录缓存串用。其余14项是明确增强。byte桶截断和负precisedelta取绝对值有既有约定，因此只提opt-in增强；naturaltime.when已有，不重复提新入口。日历端点间隔与原平均月长duration分开，默认日期字符串回传、英语列表和所有str返回保持兼容。新API命名均为拟议契约，不宣称源码已有定义。

路线逐项包含需求/原观察/真实模块/正常与边界验收/原生回归/实际依赖，20项不依赖前一步完成。翻译形态和数量级profile仍需要语言维护者审阅；本轮只核对现有实现与复现输出，不冒称完成各语种语法审校。完整原版通过不代表增强已通过。

## 证据与重跑

证据位于.deploy/github-100-research/resume-app/humanize，包含官方元数据、commit、issue、许可源码、安装及冻结依赖、原生JUnit/log/result、翻译准备记录、20观察、20步JSON和SHA256清单。项目根可运行：

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-app/humanize/venv/bin/python .deploy/github-100-research/resume-app/humanize/observe.py
```

完整基线命令见baseline-result.json，先将gettext-tools/root/usr/bin加入PATH并将对应usr/lib/x86_64-linux-gnu加入LD_LIBRARY_PATH，再按上游脚本构建.mo。跨机器应从官方URL检出同commit、按冻结依赖重建独立venv、编译翻译资源并核对实际导入路径；本机绝对路径不等于可移植交付。未来冻结阶段仍需离线制品封存。上游git干净，无正式库变更、路线实现、提交推送部署或上游消息。
