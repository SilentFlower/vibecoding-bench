# 部署迁移执行计划

1. 读取本任务材料与平台/网关相关规范，记录现有组件内容摘要、文件blob/执行位和保护基线。
2. 搬迁受控部署源文件与夹具，完善source_path部署映射；保留旧固定包目标和服务归属。
3. 修正源码版本读取、安装模板摘要、容器源码挂载验证器及子进程入口；按调用方核对旧路径余项。
4. 增加flower2api-stack，保持v3-stack兼容转发；删除迁入网关的两份工作流。
5. 同步根CI、缓存指纹、README、SOP和有效规范的机械路径。准备默认main的三个注册文件投影。
6. 增加新旧部署布局、上一版单仓、固定宿主、新文件缺失拒绝回落及CLI转发回归。
7. 在仓库根验证：
   - PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s deploy/flower2api
   - .venv/bin/python deploy/flower2api/verify_database_definitions.py
   - PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator -p 'test_system_update*.py'
   - actionlint覆盖根构建/发行与默认main投影；bash -n检查两脚本；检查JSONL和当前文档链接。
   - 比较两角色组件内容摘要、迁移定义及登记字节，核对受控文件执行位。
8. 使用新目录入口实际构建同批候选，再用.venv/bin/python deploy/flower2api/verify_system_update.py --migration-manifest <同批候选清单> --output <本任务隔离证据>验证安装、升级、回退和中断恢复。使用合成密钥、临时目录与本次Docker资源。
9. 经Check-All、Update-Spec及精确Git计划交付；生产发行和安装按后续独立明确动作执行。
10. 将最终源码入口和本轮规范路径变化交接给规范整理子任务。
