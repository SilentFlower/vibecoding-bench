# 生成项目原理介绍 HTML

## Implementation Checklist

- [x] 阅读 README、WebUI 静态资源、docker-compose、orchestrator、sidecar 和 worker 入口脚本，确认页面内容依据。
- [x] 确定 HTML 放置位置和入口方式，优先选择不影响现有 WebUI 的静态页面。
- [x] 编写项目原理页面，覆盖架构、执行流程、容器网络、数据落盘、WebUI 联动和关键限制。
- [x] 根据现有前端风格补充必要样式，保证桌面和移动视口可读。
- [x] 本地打开页面或启动静态服务验证资源路径、布局和无明显控制台错误。

## Validation

- 打开生成的 HTML 页面进行人工检查。
- 如修改 `webui/` 资源，验证现有 WebUI 主要页面仍可访问。
- 如仓库存在适用的 lint/test 命令，再运行对应检查；若没有，记录手动验证结果。

## Review Gates

- 页面内容必须以仓库现有 README、代码和配置为依据。
- 实现前确认不修改后端行为、不新增构建链路。
