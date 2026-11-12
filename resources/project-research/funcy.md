# Funcy 单仓研究

研究日期2026-10-21。来源、固定源码、许可、适用完整原生基线、业务场景和[20项研究路线](./funcy-roadmap-20.md)已完成；路线尚未实施。

## 来源与许可

官方[Suor/funcy](https://github.com/Suor/funcy)和[完整提交](https://github.com/Suor/funcy/commit/e8febffd57f80db8ca3a55fb1edd0feee2290d61)已网页核对。固定`e8febffd57f80db8ca3a55fb1edd0feee2290d61`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy/source`工作树干净。主仓BSD三条款，保留Alexander Schepanovski2012-2026。objects.cached_property注释声明借自Django，已核其对应年代BSD3许可并保存Django1.4 LICENSE，确切复制版本未被本仓标记。seqs.ilen明确引用SO答案15112059，原答作者zuo、2013-02-27且可见末次编辑同日；按[SO官方许可时间规则](https://stackoverflow.com/help/licensing)对应CC-BY-SA3.0来源，不能声称根BSD自动替代该归属/条款。docs/_static/nhpup_1.1.js保留Nicolas Höning2014及MIT全文。third-party-license-verification.json逐项记录；只研究，正式分发前需保留对应来源条款，不对短算法版权门槛作法律判断。

## 源码、依赖与成本

已读签名Spec/Call/curry与TypeError路径、缓存memory/key/失效/expiry、once与retry/fallback/context、缓存property/惰性对象、集合factory/浅合并/复制路径、惰性窗口/tee与树遍历。贡献规范要求真实用例、小改动与常用路径性能比较；未来路线为候选，不宣称上游已接受。

实际跟踪69文件、293827字节；独立测试venv 41143410字节。运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。 精确freeze和安装报告已保存。依赖准备宿主Python3.12.3，安装11.781秒；**测试镜像Python3.12.15**，sys.version及镜像ID在runtime-verification.json。无需外部服务。

## 原生基线与真实场景

复用已冻结完整原生tests -W error证据：260通过0skip/xfail/失败错误，符合tox；未为报告重跑。pytest7.4.3和whatever0.7与上游requirements一致。 实际260通过、0跳过、0失败、0错误。墙钟1.734秒，pytest XML时间0.849秒，进程峰RSS 36036KiB；容器预算512m无额外swap、pids128、离线、UID1000、源码和依赖只读，未OOM且容器已删除。

真实订单tea数量2+3、coffee1，group_by+pluck+walk_values得到tea5/coffee1，原订单不变；新probe加载/source/funcy。逐项实跑内部TypeError被autocurry吞掉、缓存属性别名重复计算、once失败后noop、generator上下文时机等。只有前两项按原版实证缺陷处理，其他当前行为列为显式增强。

## 路线真实性与限制

已有monotonic TTL cache、key_func、invalidate/invalidate_all、SkipMemory、位置/关键字缓存键隔离、once_per不可hash参数、retry动态timeout/filter_errors、reraise cause、lzip(strict)、滑动step与短尾chunks、get_lax/get_in/set_in/del_in、Call posonly/kwonly、list/惰性族均不重复计入。

20项每项均有来源、场景、原版/替代、真实模块、兼容边界、正常/异常验收、原生回归和依赖。2项实跑问题，其余为显式增强。2项实证修复与18项完整普通增强；异步序列核心族合为一步，路径适配/树遍历/深层重建/关系join各有不同输出与验收。没有改正式库或执行未来改进。

- 未跑独立Sphinx/flake8与其他Python/PyPy矩阵，保留原生warnings-as-errors成功集合
- 原仓未逐文件标记Django借用版本，SO引用源条款与根BSD不能直接等同；本轮已识别并记录，未进行产品分发或声称完成该来源的再分发准备
- 仅验证当前Linux/CPython3.12.15；其他Python、PyPy、Windows未运行
- 20步未实施；独立冻结验收、正式接入、提交推送及部署未开始

## 证据与复跑

证据根`/root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy`保存安装/精确freeze、baseline-tests.log/xml、baseline-result.json、size.json、observe.py与观察日志/JSON、runtime-verification.json、official-source-verification.json、research.json、roadmap-20.json、review-result.json和evidence-sha256.json。原生复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy/run_python_baseline.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy --memory 512m --tests tests
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/funcy
```

不把原生通过等同于20步新增验收通过，没有实施路线或修改正式内容库。
