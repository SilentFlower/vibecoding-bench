# 额度本轮完成实施计划

## 顺序

1. 读取任务三件套及额度、账号运行时、前端规范，确认无窗口代码尚未落地的隐式依赖。
2. 搜索所有 `_enforce_running_quota`、on_running、强停常量和 stopped 专用判断；仅撤除百分比运行中强停，保留通用停止/恢复收口。
3. 同步真实运行回归、下一轮门禁测试及既有停止兼容，核对 v3 normal/warmup passthrough。
4. 将本地 driver/浏览器强停验证改为本轮完成验证，同步 UI 文案、导入、参数别名和相关 README 段落。
5. 运行聚焦检查与真实离线验证，保存证据；再进入 Check-All 和规范更新。

## 验证命令

优先复用已安装 orchestrator requirements 的 Python 环境；真实命令及退出码写入检查证据。

```bash
python3 -m unittest discover -s orchestrator -p 'test*quota*.py'
python3 -m unittest discover -s orchestrator -p 'test_auto_usage.py'
python3 -m unittest discover -s orchestrator -p 'test_account_runtime.py'
node --check webui/app.js
```

更新验证入口后，按它实际支持的参数运行隔离 driver 和浏览器场景；manifest 使用正式验证构建输出的同批文件，不借用生产部署或受限账号。原强停测试文件若更名，同步 discover 和导入，不能留下旧预期。

## 风险与回退点

- 运行中真耗尽与自设阈值不能混写；保留现有 quota_wait 与永久认证门禁。
- 终态发布前的最后被动消费是下一轮门禁依据，不能随强停函数一起删掉。
- 删除回调后必须验证实际 driver 继续、下一轮不启动，不能只以 mock 未调用 cleanup 判定通过。
- 本子任务不改 schema；失败时回退对应精确产品 diff，保留已有数据和其它工作区改动。

## 实施记录

运行中百分比强停及等待回调已撤除，终态前被动消费、下一轮门禁和历史停止意图保留。10 项本轮完成回归、最终全量 415 项后端测试、四个真实 driver 场景和 b 批浏览器兼容验证通过；清单、命令及日志见父任务 `../10-20-v3-environment-panel-and-run-windows/implement.md`。整体检查及规范同步通过，业务代码已推送，未部署生产。
