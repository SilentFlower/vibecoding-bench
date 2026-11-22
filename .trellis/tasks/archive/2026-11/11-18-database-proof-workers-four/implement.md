# 实施计划

1. 读取相关平台构建/历史演练规范与真实代码、测试，核对1/2校验、失败收口、原子证据和容器资源参数。
2. 将API/CLI范围扩为1、2、4，新增真实四路屏障与失败收口测试。
3. 增加Linux主机范围性能采样与受控事件，采样成功/缺失、异常以及线程退出均定向验证。
4. 执行原兼容测试与安全参数回归；用隔离真实Docker和相同历史集合进行2/4对照，记录样本来源与资源边界。
5. 根据实测确定工作流4路配置，更新SYSTEM-UPDATES.md及平台权威规范。
6. 运行平台完整发现、工作流actionlint及git diff --check，进入Check-All、Spec评价和精确Push。

## 验证入口

- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_database_compatibility test_system_workflow test_system_build_cache`
- `PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s deploy/flower2api`
- actionlint检查`.github/workflows/v3-release.yml`
- 真实Docker对照沿原verify_database_compatibility入口，私有合成信任材料与临时数据在gitignored运行目录生成，仅清理本次归属资源。

## 完成与衔接

通过本子任务验收后推进运行时版本兄弟任务。正式发行和生产安装沿后续明确授权；当前性能结论只覆盖实测环境。
