# 后续外部验收

## 推送后的构建与入口

- 责任：本任务交付会话在批准推送后核对GitHub Actions。
- 动作：核对flower2api提交触发的v3-build.yml使用deploy/flower2api命令，合同测试及两镜像构建成功；核对默认main注册的手动构建、发布入口和目标分支准入。
- 预期：构建通过；正式发行保持workflow_dispatch及publish显式确认门禁。
- 记录：保存实际run链接、SHA、结论及构建清单，失败沿对应任务恢复流程处理。

## 后续规范整理

最终源码目录与来源映射交接至同父任务下的flower2api-spec-consolidation，继续核查过期、冲突和重复规范，以及cc2api/runtime协议经验去向。
