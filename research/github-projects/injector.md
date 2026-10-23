# Injector 单仓研究

研究日期：2026-10-21。官方来源、固定源码、完整默认原生测试/覆盖门槛、实际对象装配和[20项路线](./injector-roadmap-20.md)已研究完成；路线未实施、冻结验收和平台接入尚未完成。

## 来源与许可

官方[python-injector/injector](https://github.com/python-injector/injector)与[完整提交](https://github.com/python-injector/injector/commit/5daed12510fafc0bf73b6ef18d2884f78cd5e210)已网页核对，固定`5daed12510fafc0bf73b6ef18d2884f78cd5e210`，检出`/root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector/source`，工作树干净。git remote指向当前官方组织，setup.py仍有alecthomas旧地址，只作为同一仓库别名不重复计数。BSD-3-Clause，保留COPYING中的2010 Alec Thomas/Google Inc.版权、源文件头及SwapOff.org不背书条件。核心/测试扫描未见独立vendor或样本许可。

## 真实模块与轻量成本

跟踪33文件、191303字节；测试venv 52179413字节。核心`injector/__init__.py`约1680行，已读Provider/ClassProvider/CallableProvider/InstanceProvider、Binding/Binder、MultiBinder及map/list、Scope/Singleton/ThreadLocal、Injector.get/create_object/call、注解过滤、BoundKey/AssistedBuilder和Module安装；并对照README/scopes/practices说明。生产requirements.txt为空，不需要服务、数据库或云凭据。依赖准备宿主Python3.12.3，安装12.196秒；原生执行容器Python3.12.15，镜像ID/sys.version见runtime-verification.json，精确测试依赖在requirements-frozen.txt。

## 基线与真实场景

复用本目录父代理已实跑的完整默认pytest，核对commit、干净工作树、日志/XML、运行脚本及当前定义。上游默认含README与模块doctest、分支coverage和**90%门槛**；实际**145 passed、0 skipped/xfail、0失败错误，coverage96.93%**。墙钟3.855秒、pytest XML时间2.461秒、最大RSS 58208KiB。首次只读目录无法写coverage的结果保留于readonly-first-attempt；最终复制原版源码到容器/tmp/working后原样执行，未改源码/测试/门槛，原检出保持只读。coverage数字由原始日志证明，临时html/xml未单独拷出。

镜像内UID/GID1000、无网络、只读根、512MiB无额外swap、pids128，临时容器已删除、无OOM。未跑其他解释器/平台、mypy/lint/Sphinx文档。新跑本地格式器场景：Injector构造Formatter并注入Prefix，实际输出item:tea；加载`/source/injector/__init__.py`，观察exit0、0.485秒、256MiB，容器删除。逐项观察明确复现非注入注解失败、BoundKey漏剩余注入、dataclass排除失效和Module类构造注入失约；其余是显式新模式，不能把全部作用域诉求称为BUG。

## 20项与交付边界

每项包含来源/真实场景、原版/替代、交付、实际模块、兼容、正常/异常验收、原生回归与实际依赖。父子聚合、共享singleton、资源管理、异步provider、任务scope、根解析scope、缓存失效分别有不同的生命周期和实例身份目标；静态图检查与运行trace也分开定义。已有auto_bind=False、ProviderOf、AssistedBuilder、Annotated保留等未重复计步。全为普通本地软件对象组装，不涉及账号或网络机制。

## 证据与复跑

本地`/root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector`包含baseline-tests.log/xml、baseline-result.json、run_native.py、readonly-first-attempt、observe.py及观察结果、依赖锁/安装报告、size.json、runtime-verification.json、来源/许可记录、research.json、roadmap-20.json、review-result.json及evidence-sha256.json。复跑命令：

```bash
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector/run_python_probe.py /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector
.deploy/github-100-research/resume-core/attrs/control-venv/bin/python /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector/run_native.py baseline /root/project/vibecoding-bench/.deploy/github-100-research/resume-main/injector --memory 512m
```

取证依赖与镜像是本机准备物，不能把文档当作跨机器就绪的运行包。没有实施路线、修改正式内容库、提交推送或部署。
