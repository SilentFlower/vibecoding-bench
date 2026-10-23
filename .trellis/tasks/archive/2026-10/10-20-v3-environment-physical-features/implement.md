# 物理特征面板实施计划

## 顺序

1. 加载后台运行环境、真实资源指标和前端组件/状态/质量规范，读取已有 DTO、runtime 归属/锁和采集函数。
2. 增加白名单探针、严格输出校验、私有缓存及配置/观察对照，接入受限只读采集端点。
3. 扩展环境详情 UI、采集按钮、来源和时间提示，保留原维护动作。
4. 补充来源/失效缓存/停止/占用/错误/资源口径测试，并运行实际本地容器采集验证。
5. 本地页面/API/文件核对后进入 Check-All、Update-Spec，记录与后续 P2 接入的时区字段。

## 验证命令

```bash
python3 -m unittest discover -s orchestrator -p 'test_physical_features.py'
python3 -m unittest discover -s orchestrator -p 'test_account_runtime.py'
node --check webui/app.js
```

新增聚焦物理特征测试及本地浏览器场景；实际容器验证复用 deploy/v3 的隔离构建/启动工具，核对 API、页面及 runtime 快照，不调用真实模型。已有验证入口的精确参数在接入后记录，禁止用生产面板代替本地验收。

## 回退与风险

- 采集不得经过 ensure 或画像补齐；过期快照必须保留来源和时间。
- 对保存值的展示必须基于已有字段定义，未知项不猜；私有缓存不保存配置以外的秘密。
- 回退仅撤除新端点/模块/页面，不删除身份、HOME 或其它 runtime 数据。

## 实施记录

白名单探针、私有快照、公开对照及显式采集均已接入。聚焦测试、最终全量 415 项后端回归、b 批镜像的物理实测与浏览器验证已通过；命令、清单及日志统一记录在父任务 `../10-20-v3-environment-panel-and-run-windows/implement.md`。父任务整体检查及规范同步通过，业务代码已推送，未部署生产。
