# 已确认的来源与复现

- 用户选择04节点花冠，随后确认粉红纯图形版本。参考文件：.trellis/.runtime/flower2api-brand-preview/flower2api-mark-04-pink.png，SHA256：8d548cf7a6421df9ebcfc2a4febbaca08ac05b3c25484ffbb3362901dd48362a。
- 原生dialog的旧margin为0；1280x900旧位置(0,0)、恢复auto后(384,271.5)；390x900旧位置(0,0)、恢复后(16,247.5)。原始实验在.trellis/.runtime/flower2api-legacy-package-cleanup/ui-dialog-position-inspection.json。
- 页面投影读取account_runtime.py:806起；环境/内核代次核对位于约835行，新鲜度45000毫秒；原生巡检checking字段源于gateway/native_prewarm.rs。生产只读样本保存于前述runtime目录native-status-inspection.json，两个原生账号均ready且身份匹配。
- environments.js:26起为轮询，finally在有原生摘要时设置20000毫秒；146起为渲染；当前浏览器验收覆盖过期/preparing/ready，缺少截图对应检查中未匹配的明确展示与居中几何断言。
- 选定图形工具输出为白底PNG；正式网站图标采用原有SVG资源机制整理透明图形，保留选定结构与粉红色。

- 新截图复制失败已定位：RequestDiagnostics.vue:205直接writeText并统一失败提示；Accounts.vue:853起具有安全上下文及textarea降级，Tokens.vue:137有较简降级。DialogContent采用Reka的DialogPortal/Content，降级节点需要考虑其焦点域。
