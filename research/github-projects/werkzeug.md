# Werkzeug：真实 GitHub 项目研究

研究完成；来源许可、固定源码、适用完整原生基线与普通业务场景已实际核对，形成[20个独立工程交付及验收边界](./werkzeug-roadmap-20.md)。**仅研究，未实施路线、未冻结独立验收、未接入正式内容库。**

## 官方来源与许可

官方仓库 [pallets/werkzeug](https://github.com/pallets/werkzeug)，固定完整提交 [`665e760ca6325a348ce03e5cf780b17e4be01848`](https://github.com/pallets/werkzeug/tree/665e760ca6325a348ce03e5cf780b17e4be01848)，源码版本 `3.2.0.dev`。官方仓库元数据、commit元数据、detached checkout与revision.txt对应，已读取 LICENSE.txt：BSD-3-Clause，保留Pallets版权、三项再分发条件与免责声明，不能以作者姓名背书。

工程跟踪 **294 文件、2,374,095 字节**，142个Python文件共 **37,474行**（包括测试与工具）。未将原工程改成同构入口。已读取路由状态机/MapAdapter/Converter定义、MultiDict/CombinedMultiDict、Headers、FileStorage/FileMultiDict、Request表单扩展路径、sansio multipart、Response JSON/stream、Client/TestResponse和相关原生测试。旧 FormDataParser 正处于弃用迁移期，路线以现有 Request._parse_form_data 与实际源码边界设计，不拿旧教程推定现版接口。

## 原生基线和轻量程度

本机独立证据环境 `.deploy/github-100-research/resume-app/werkzeug/` 下保存 source、venv与isolated-home。Python **3.12.3**、Linux x86_64。实际安装源码及上游测试依赖 cffi、cryptography、ephemeral-port-reserve、pytest、pytest-timeout、watchdog，并为原生测试安装requests；安装 **12.389秒**，venv **71,149,601字节**。精确依赖见requirements-frozen.txt，包括pytest9.1.1、MarkupSafe3.0.4、watchdog6.0.0、cryptography50.0.2、cffi2.1.1；非纯标准库运行成本已明确记录。

完整原生默认pytest：**1019通过、0失败、0错误、0跳过**；耗时 **13.13秒**，测试进程峰值RSS **130,504KiB**。完整集合包含上游本地开发服务器测试，并已结束；不能将该基线误述为完全没有本地套接字测试。业务观察脚本使用内存WSGI Client、不监听端口；不访问外部业务系统，无账号、凭据、数据库或云服务。其他Python/OS矩阵、文档构建、lint/type检查未跑，不算已验证。

## 真实业务使用与原版观察

observe.py 从本轮固定检出导入，observations-result.json.module 指向 resume-app/werkzeug/source/src/werkzeug/__init__.py。原生 Request.application + Client 执行中文商品查询及重复数量2/3，JSON响应正确。脚本保存20个观察键，分别对照每步现状与公开入口缺口。

两项修复均有原版实跑反例：[官方#3156](https://github.com/pallets/werkzeug/issues/3156) 的无关规则使 /foo 从one变two；[官方#3285](https://github.com/pallets/werkzeug/issues/3285) 的同一个空表单字段整块解码为空，逐字节却多出0d。每个缺陷族只计一步，不按converter或chunk矩阵拆数。

其他18项均标为研究者增强提案：重复参数诊断/来源/合并/单值消费、元数据事务更新、文件原子保存/回执/资源作用域、批量链接构建、匹配解释、精确金额/日期/枚举converter、客户端记录、受控流测试、解析诊断、表单分段迭代与NDJSON读取。已明确现有getlist忽略转换错误、update追加、pop删除整个键、AnyConverter返回字符串、FileMultiDict.close/clear、CombinedMultiDict.copy、低层MultipartDecoder、iter_encoded和TestResponse.request/history能力，不把现有约定伪报缺陷。增强入口不存在的观察与相关源码检查共同支持提案；无上游接受承诺。

## 证据与重跑

证据根 `.deploy/github-100-research/resume-app/werkzeug/`：repository.json、commit.json、revision.txt、安装记录与requirements-frozen.txt；baseline-result.json、baseline-tests.log/xml/time；observe.py、observations-result.json、observations.log；roadmap-20.json封存逐步ID、来源、观察、实际模块/回归路径与依赖；review-result.json与evidence-sha256.json用于复核。旧cli-config证据保留，本报告不再引用旧/tmp导入路径。

在项目根重跑普通场景：

```bash
HOME="$PWD/.deploy/github-100-research/resume-app/werkzeug/isolated-home" .deploy/github-100-research/resume-app/werkzeug/venv/bin/python .deploy/github-100-research/resume-app/werkzeug/observe.py
```

在source目录设置相同隔离HOME，运行独立venv的 `python -m pytest -q -ra -p no:cacheprovider --junitxml=<证据目录>/baseline-tests.xml` 重跑完整基线。异机先clone官方仓库并detached checkout上述完整commit，按冻结依赖创建独立环境，将editable项替换为本地固定检出，核对导入路径后执行。首次安装依赖源可达，未来冻结验收前还需离线wheelhouse；本机证据不是跨机器可用性保证。

本轮上游源码git工作树干净；没有改正式库、产品代码、生产或账号数据，没有提交、推送、部署、向上游发消息或实施二十步路线。
