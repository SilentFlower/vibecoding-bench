# Natsort 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./natsort-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[SethMMorton/natsort](https://github.com/SethMMorton/natsort)和[完整提交](https://github.com/SethMMorton/natsort/commit/e9a3a2a307580a1f2be8c57bba50fba45789ada0)已网页核对。固定`e9a3a2a307580a1f2be8c57bba50fba45789ada0`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort/source`工作树干净。MIT，保留LICENSE的Seth M. Morton2012-2023归属。unicode_numeric_hex是本仓dev/generate_new_unicode_numbers.py从Python unicodedata生成的码点事实列表；未把Unicode标准文本当作本仓原创授权。可选fastnumbers/PyICU及未来packaging各保留独立许可。

## 源码、依赖与成本

已读预编译工厂链、Unicode归一化/数字regex、str/bytes/number/nested/path分派、locale数值分隔与collator、INT/FLOAT回退、keygen/索引排序及CLI读取/筛选/输出。已经有较完整泛型注解，未拿类型声明凑为新能力。

实际跟踪61文件、283896字节；独立测试venv 58131020字节。默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装18.094秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

上游slow-tests Hypothesis profile与coverage保留：完整tests362通过，1跳过为缺cs_CZ locale；coverage92%无原生门槛。另上游module/README/examples/howitworks示例统一入口15通过0skip；howitworks按上游IGNORE_EXCEPTION_DETAIL设置，其他三个集合未含Traceback示例。 实际362通过、1跳过、0失败、0错误。墙钟17.867秒，pytest XML时间15.396秒，进程峰RSS 265220KiB；容器预算512m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实章节文件chapter10/2/1排为1/2/10，记录按chapter字段返回label A/B，实际加载/source/natsort。另CLI默认整数排除相邻16位编号实跑确认精度误删；float超范围按已声明float语义处理，精确模式列为增强而非无依据缺陷。首次观察因--help正常SystemExit0导致脚本未打印JSON，保留help-exit-first日志，修正控制脚本捕获该退出后重跑通过，未修改上游。

## 路线真实性与限制

已存在INT/FLOAT/SIGNED/NOEXP/NUMAFTER/PATH、Unicode数字、NFD/NFKD、locale、大小写组合、NANLAST、PRESORT、nested key、索引排序、os_sorted、PureWindowsPath对象及CLI-z输入；不重复计为新增。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。1项实跑问题，其余为显式增强。1项CLI整数精度实证问题与19项普通排序增强。精确数字、版本/单位/日期适配均为显式策略，不把自然排序冒充领域解析；外部排序仅本地临时文件，未来可选依赖仍需冻结版本许可。

- 未运行可选fastnumbers/PyICU后端和cs_CZ locale的1个原生场景；英语/德语系统locale适用用例已运行，报告不宣称全部locale通过
- 未跑ruff/mypy/Sphinx与所有操作系统；核心已有类型注解不代表本轮类型检查通过
- 未来packaging/ICU等适配未安装/实现，其正反验收仍是计划目标
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort --memory 512m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-core/natsort
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
