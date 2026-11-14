# 执行与验证

## 计划

- [x] 核对现有规格、ensure全部调用者、实际sender配置与资源定义，进入inline实施路由。
- [x] 增加显式准备职责并复用现有生命周期，覆盖首次和已存在布局，保留API严格预检。
- [x] 同步所有CLI/管理消费者及受控预算故障说明，回归未知启动保护和原目标人工恢复。
- [x] 增加有意义的缺预算/不足预算、现有native布局、API并行/维护、身份及秘密隔离测试。
- [x] 运行Python定向和完整测试集，以及实际Docker隔离环境零模型准备验证；按实际变更运行所需构建和跨层校验。
- [x] Check-All修复与重检。
- [x] Update-Spec及精确Push计划。
- [x] 业务推送后按SOP完成v1.6.2正式发布与验签，再完成任务进度和记录提交。

## 验证入口

- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_account_runtime test_native_sender test_startup_recovery test_projects_runtime_resilience test_projects_terminal test_main`
- 完整集：unittest discover services/orchestrator。若宿主长进程受终止，使用按发现结果逐模块隔离执行并核对发现/执行总数的等价完整测试，不以部分通过代替全量。
- 实际隔离环境：复用deploy/flower2api的Docker与回环夹具，明确native293且空sender预算、有限1536m，完成CLI准备但不发送真实模型请求；API准备受控拒绝且发送计数0。
- `python3 deploy/flower2api/verify_database_definitions.py`、`git diff --check`及按影响选择的发布/源码快照合同。

## 风险与恢复点

- applied与desired布局混淆、实际sender预算被覆盖、CLI触发重建影响在途API。
- 首次基础布局被误用为native业务回退；必须沿严格transport在投递前拒绝。
- 人工恢复原未知启动须继续证明现场安全，不能清空失败记录或重放输入。
- 起始保留397个无关dirty路径，沿自动任务baseline逐项核对并保留。

## 验证进展

- 定向210项通过（环境、sender、恢复证明、两空间运行韧性、工程终端及main）。
- 数据库定义检查通过，bench/gateway均保持版本1；git diff --check通过。
- 完整Python发现集按模块独立进程执行中；真实Docker已完成首次三角色准备，停止后恢复及API受控拒绝均通过；真实三角色资源为network256m/sender128m/CLI1152m，容器ID保留、代次1→2、模型调用0。

- 版本元数据已递增为v1.6.2并写入本轮修复说明；发布合同定向回归与完整Python回归继续核对。

## CHK-001修复续行

- 用户已选择修复全部；沿当前inline实现与重检路由补齐独立评审和系统更新rebuild/restore入口。
- 两个入口均按已生效布局准备CLI；API transport与显式预热保持严格默认。
- 增加真实评审准备边界与HTTP更新恢复回归，覆盖native293、1536m及空sender预算；继续定向、全量重检与原发版流程。

- CHK-001已修复：145项定向通过；补充的HTTP场景覆盖基础/native布局的rebuild与restore，沿冻结资源恢复。
- 修复后完整发现与执行均1281项（88模块），全部通过，跳过1项。Check-All重检通过，剩余CHK/FBK为0。

- Update-Spec已写入2份权威规范，源码反向核对、差异及只写规范边界检查通过；进入精确Push和已授权发布的统一计划。

## 首轮发布验证恢复

- 业务源码已同步，首轮发行run 43584267140在系统更新测试阶段退出。新增合成三角色测试在普通UID执行真实chown，触发权限异常。
- 测试夹具改为同时模拟os.chown、os.fchown和os.chmod；真实归属与只读保护继续沿独立Docker证据。
- UID1001禁网容器的系统更新17项通过，宿主root定向1项通过；按CI原命令再次核对后继续精确提交及正式发布。

## 正式发行验收

- v1.6.2发行：https://github.com/SilentFlower/vibecoding-bench/releases/tag/system-ci-43585521381-1。流水线43585521381全部通过，绑定补充提交89f198f3。
- 双镜像源码摘要、6项附件摘要和Ed25519签名通过；迁移目录序号216/1、原目录196/1均独立验签通过。
- 正式8来源旧库升级及旧程序回退演练通过。线上安装及11-14原目标实际恢复沿release.md验证。
