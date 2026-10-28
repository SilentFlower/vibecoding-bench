# 工作区命名核对

- `ProjectsTerminal._workspace_identity`（`orchestrator/projects_runtime.py:48`）是两空间共用的名称来源。普通首轮有专门历史兼容分支，其他情况把 namespace 写入可见目录名。
- `_prepare_workspace`（同文件 `:73`）同时决定物化 seed、工作区注册和输入凭据；输入凭据合入完整身份，其摘要决定文件名，故旧身份不能静默补字段。
- `_registered_identity`（同文件 `:165`）与 `cleanup_cycle`（`:178`）重新推导别名，并通过前缀判断孤立目录。新名称必须同步这两处的归属核对，不能只改生成前缀。
- `PiTerminal.start`（`orchestrator/pi_terminal.py:60`）从 `workspace.name` 计算真实 cwd；其 `:114` 按 cwd 构造主 Claude JSONL 位置。历史项目直接改名会改变恢复入口。
- `ProjectDefinition`（`orchestrator/project_library.py:184`）只有 root 和 manifest；`ProjectsCatalog.project`（`orchestrator/projects_catalog.py:56`）提供项目 key 和中文展示标题。命名可复用已验证的英文项目 key，无需翻译标题或修改冻结内容。
- 示例真实项目 key：`python-frontmatter`、`mistletoe`、`sqlite-utils`。其 project.json 标题分别带文档资料／知识库／数据整理场景说明，属于页面字段。
- `test_projects_cycles.py:42` 明确断言普通历史首轮路径及四字段注册完全兼容；应保留为显式旧夹具，另加新建命名测试，不能只把旧期望替换成新名称。
- `test_projects_workspace.py` 使用真实目录覆盖累计成果、目标材料补齐、旧基线不扩写及链接拒绝，可扩展为两空间共享回归。

本次只进行只读调查和规划文档写入，尚未修改业务代码或操作生产。
