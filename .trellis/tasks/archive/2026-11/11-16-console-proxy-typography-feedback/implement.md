# 实施与验收计划

## 0. 开工条件

- [x] 完整Brief评审通过后由`task.py start`进入in_progress；内联执行。
- [x] 按implement.jsonl读取规范、确认类型和调用方；记录当前无关dirty基线，限定本任务范围。
- [x] 核对新增任务代理保存的锁顺序、配置比较和关联竞争测试，再实现跨服务写入路径。

## 1. 公共阅读尺寸与反馈基础（R2/R3/R4）

- [x] 固定改动前390/1440/1920/2560/3440的相关页面和弹窗截图；记录CSSOM字号与布局。
- [x] 新建单一共享基础CSS，接入Vue、原生兼容页和原型；同步构建与静态桥白名单。
- [x] 提取通知、确认、操作结果公共组件；保留现有调用兼容，增加本地组件预览。
- [x] 逐页迁移硬编码小字与必要控件尺寸：账号、代理、令牌、请求、设置/更新、运行环境、任务六分区及其弹窗。保留四列、费用摘要和所有功能入口。

## 2. 任务代理专用交互（R1/R4）

- [x] 为任务列表增加批量目录公开投影；验证关联权威、目录外、缺失、直连与同步别名。
- [x] 新增受控选择快照/保存接口及类型；Rust解析目录，独立任务沿原维护锁提交，关联任务复用网关许可与单字段更新。
- [x] 覆盖原配置/关联/目录版本冲突、忙碌、直连、重复提交、锁释放与私有字段隔离；回执不确定时提示先回读。
- [x] TasksWorkspace挂载专用选择窗口，复用ProxyPicker；卡片简洁显示目录名称，详情显示公开观测。
- [x] 验证取消零写、草稿保留、路由/筛选/滚动/焦点稳定、授权登录和完整账号编辑入口继续可达。

## 3. 页面反馈迁移（R3/R4）

- [x] 账号测试改为按账号和请求代次维护，固定位置结果，完整错误与重新测试。
- [x] Vue通知消费者迁入共享宿主；原生控制器通过runtimeScope适配共享通知/确认，独立文档保持兼容。
- [x] 统一代表性删除、维护、表单保存、批量检测反馈；保留业务影响说明、禁用和失败恢复。
- [x] 覆盖并发两账号、同账号重复、请求乱序、长错误及键盘回归；核对离页撤销及减少动画的生命周期分支。

## 4. 验证命令与证据（A1～A8）

按实际变更执行，成功证据在同一变更集内复用；新失败或进一步修改才重跑相关范围。

基础检查：

```sh
npm --prefix apps/web run build
node --check apps/legacy-web/app.js
node --check apps/legacy-web/projects.js
node --check apps/legacy-web/environments.js
cargo fmt --check --manifest-path services/gateway/Cargo.toml
cargo test --locked --manifest-path services/gateway/Cargo.toml
python3 -m unittest discover -s services/orchestrator -p 'test_proxy*.py'
git diff --check
```

沿已有本地fixture扩展验证，脚本读取真实dist、拦截合成API：

```sh
python3 deploy/flower2api/verify_task_login_design.py
python3 deploy/flower2api/verify_proxy_design.py
python3 deploy/flower2api/verify_task_feedback.py
python3 deploy/flower2api/verify_runtime_workspace_design.py
python3 deploy/flower2api/verify_shared_pagination.py
python3 deploy/flower2api/verify_native_environments.py
```

增加一个聚合场景脚本覆盖新选择快照与失败、账号测试状态隔离、全站字号/浮层和代表性通知确认；字体与相关新组件预期以本任务更新的原型为准。复用原截图采样脚本，更新确实受影响的预期；禁止单纯放宽断言掩盖差异。

视口矩阵：390、1280、1440、1680、1920、2560、3440 CSS像素；另外验证浏览器125%/150%等效CSS视口、侧栏展开/收起与代表性短视口。提交截图和CSSOM摘要到gitignored验证目录，在任务记录关联证据路径。

## 5. 复核与收尾

- [x] Check-All检查跨服务字段、维护锁、请求取消/迟到响应、公共控件复用、入口完整性和模板资源路径。
- [x] 根据代码与测试更新web UI、gateway代理目录及必要orchestrator规范，消除旧字号/宽度冲突。
- [x] 汇总三组验收结果，完成统一Brief范围检查，再进入精确提交推送计划。

## 主要影响位置

- `apps/web/src/{api.ts,App.vue,main.ts,*design.css,style.css}`
- `apps/web/src/components/{Accounts.vue,TasksWorkspace.vue,ProxyPicker.vue,RuntimeEnvironments.vue}`、相关业务弹窗、`runtime/runtimeScope.ts`、`ui/`与`composables/`
- `apps/legacy-web/{app.js,index.html,*design.css}`及共享基础CSS；`apps/web/runtimeModule.ts`
- `services/gateway/src/{handler/router.rs,service/runtime_bridge.rs}`及任务代理解析/保存辅助模块
- `services/orchestrator/{main.py,proxy_sync.py}`及任务代理维护辅助模块、相关测试
- `doc/design/flower2api-concept.html`、`apps/web/src/previews/UiPreview.vue`、`deploy/flower2api/verify_*.py`、相关`.trellis/spec/`

实际文件按实现证据收敛。既有SSH凭据、线上代理数据和真实测试响应不进入任务材料、日志或fixture。
