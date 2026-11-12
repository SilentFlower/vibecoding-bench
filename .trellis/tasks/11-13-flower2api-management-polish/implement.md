# 实施顺序

1. 读取任务JSONL、三件套和web/legacy-web/orchestrator相关规范，保存新一轮精确工作区基线；核对品牌参考PNG和实际DTO/渲染入口。
2. 将已选粉红标志接入现有图标消费者，核对浅色、深色与24/40像素表现。
3. 修复SystemUpdates原生dialog定位；在现有合成浏览器验收补充桌面、窄屏、低高度几何断言及零安装写入检查。
4. 在原生准备投影与渲染的现有边界细分检查等待、身份未对齐、过期和失败；补充Python代次保护和UI文字/自动刷新的失败回归。禁止以实际进程动作刷新页面状态。
5. 补齐请求ID复制的HTTP/拒绝降级及弹窗焦点域处理，用浏览器粘贴回读或具读权限夹具确认实际值；覆盖失败提示和焦点恢复。
6. 运行npm --prefix apps/web run build；PYTHONPATH=services/orchestrator .venv/bin/python -m unittest discover -s services/orchestrator -p test_account_runtime.py。
7. 运行.venv/bin/python deploy/flower2api/verify_system_update_browser.py --output <本任务runtime目录>和verify_environment_ui.py对应浏览器验收；必要时复用verify_management_ui.py核对品牌入口和旧交互。
8. 确认源码与实际构建产物一致，执行Check-All和Update-Spec，再展示精确Git计划。正式发布归后续独立操作。

## 本轮实施与验证结果

- 用户在完整Brief展示后回复“确认”，任务已按原生入口激活。
- 登录、主导航和favicon共用粉红04透明SVG，三处版本标识同步；实际构建图标SHA256为519f60c4e4d53a0f6c86f7b044633391041d9a977002ede9848c4a323605f2df。
- 复制补齐HTTP与拒绝降级，临时节点位于活动弹窗焦点域；更新确认显式居中并支持低高度滚动。
- 原生准备增加只用于展示的checking与snapshot_pending，保持代次、45秒新鲜度和进程归属校验；轮询沿用20秒。
- npm --prefix apps/web run build通过；三个legacy JS语法检查与三个浏览器验收脚本Python编译通过。
- test_account_runtime.py定向97项通过；完整编排服务回归1239项在522.107秒内结束，结果OK，跳过1项既有可选nose2环境测试。
- verify_management_polish.py：8项真实剪贴板回读通过，三个品牌入口及24/40像素深浅背景通过。
- verify_environment_ui.py：18组场景通过，实际20秒检查中到就绪、错误原因、焦点和离页保护通过。
- verify_system_update_browser.py：6组场景通过，1280×900、390×900、390×300居中及按钮滚动可达性、冻结参数、取消/Esc/遮罩、冲突、恢复原操作ID通过。
- verify_management_ui.py：上海与洛杉矶两个时区及主题矩阵通过。所有浏览器验收真实模型请求为0。
- Check-All full：三维通过，CHK/FBK/DOC均为0。Update-Spec written：web前端规范与编排原生sender合同，规范diff检查通过。
- 精确Git交付由trellis-push继续，当前任务记录随独立记录提交同步。
