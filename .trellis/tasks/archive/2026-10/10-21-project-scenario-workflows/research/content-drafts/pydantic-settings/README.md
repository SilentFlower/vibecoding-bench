# Pydantic Settings 正式场景草案

本目录只供主会话审核与集成，尚未执行新原生验收、参考补丁校准、目标镜像回归或待测模型。5 场景、7 任务的内容清单符合当前 schema 2 草案结构；不把静态文件生成称为平台 ready。

- seed/library：完整固定上游源码，保留 MIT LICENSE；不带 .git、venv 和缓存。
- seed/app：仅公开空消费端目录说明，具体素材按任务投放；PS-TRIAGE 的模型、输入和错误均只在 disclosure 中。
- materials／disclosure：公开／条件材料分离。app.env 由公开 fixture 或控制端验证脚本在临时目录生成，不依赖镜像 COPY。
- verification：逐任务隐藏 rubric、控制端 native JSON、独立校验脚本和可达修复参考补丁。参考补丁从固定源码生成，未应用到 seed 或原上游，也尚未执行。
- environment/profile：只列已核实的运行依赖和原完整回归依赖快照；无制品、无目标运行证据，artifacts 明确为空，不能通过正式环境准入。

PS-CONFIGURE 的唯一主程序应包含 App 类，允许回答代码或 app/settings_example.py。验证脚本从冻结 PROJECT_ANSWER_FILE 提取完整主示例，使用 PROJECT_CANDIDATE_ROOT 定位候选；多份不同 App 主程序会被判为歧义，不随便取第一段。校准可用 --candidate-root、--answer-file 指定路径，但本草案未执行。

PS-UNION-FIX 使用预先核验的诊断摘要，提供 fix_with_verified_context 独立入口；诊断任务本身可以结束，不机械强迫先完成模型诊断。代码授权仅列明确库实现和测试目录；其他场景保持 BASE。

回归 JSON 冻结 library 下 python -m pytest tests -q 的适用原生集合，实际环境需补完整制品并在目标镜像实跑。默认业务 60 秒／512 MiB、回归 300 秒／768 MiB 是待实测配置，不是成功证据。环境变量在控制端用例内隔离还原，缓存用例 finally 清理。
