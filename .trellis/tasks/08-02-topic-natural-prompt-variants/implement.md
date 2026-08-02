# Topic 自然提示词变体 - 执行计划

## Implementation Checklist

- [x] 在 `orchestrator/main.py` 定义 prompt 模式类型与自然模板集合，扩展 `build_topic_prompt()` 支持 `natural` / `canonical`。
- [x] 为 `TaskIn`、`BatchIn`、`CaptureRunIn` 增加 `prompt_mode`，同步各创建路由的默认生成逻辑。
- [x] 修正养号链路为单次生成 prompt，并确保数据库持久化文本与 `scheduler.submit()` 下发文本相同。
- [x] 在 `webui/index.html` 的单任务、批次、抓包表单增加自然/规范分段控件。
- [x] 在 `webui/app.js` 同步提交 `prompt_mode` 字段，并在重复打开单任务弹窗时恢复自然默认值。
- [x] 在 `webui/style.css` 增加遵循双主题、无圆角和稳定尺寸约束的分段控件样式。
- [x] 在 `orchestrator/test_main.py` 增加规范模式稳定性、自然模板差异、DTO 默认值/非法值和养号持久化一致性回归测试。
- [x] 搜索全部 `build_topic_prompt()` 调用点，确认每条链路显式或按约定使用正确模式。

## Validation

- `python3 -m py_compile orchestrator/main.py orchestrator/test_main.py`
- `cd orchestrator && python3 -m unittest test_main.py`
- `node --check webui/app.js`
- 搜索 `prompt_mode`，核对三个 DTO、三个 WebUI 表单及对应请求体字段一致。
- 搜索 `build_topic_prompt(`，核对单任务、批次、养号、抓包没有重复生成或遗漏模式。
- 浏览器检查单任务/批次默认“自然”、抓包默认“规范”，暗色和亮色主题下控件无溢出。

## Risk And Rollback Points

- 自然模板随机选择会让未持久化的重复调用结果不同，因此所有创建链路必须生成一次后复用。
- 自定义 prompt 必须保持最高优先级，不能被 mode 包装或改写。
- 不修改数据库 schema；若实现过程中发现需要新增列，应回到规划阶段重新评审，而不是直接扩展范围。
- 前端是零构建原生 JS，字段名必须与 Pydantic DTO 完全一致。

## Review Gates

- 实现前确认 `brief.md` 与三件套一致并完成 planning review。
- 实现后先跑聚焦测试，再进入 Trellis Check-All。
