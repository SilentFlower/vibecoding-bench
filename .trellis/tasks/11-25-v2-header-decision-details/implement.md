# 实施与验证

1. 以 v1.38.0 的实际读写合同和管理接口建立旧记录回归；补入新的受管决策、无策略旧记录、三阶段有差异、截断和缺 TLS 等合成场景。
2. 在 `services/gateway/src/service/{runtime_transport,native_capture,tui_sender}.rs`、必要的账号请求组装与 `services/orchestrator/native_capture.py` 贯通可信决策数据。分别验证两种受管凭据、混用版本、采集关闭、错误与隐私预算。
3. 更新 `apps/web/src/components/NativeStageDetails.vue` 与类型，复用已有控件和状态。验证筛选、行高亮、统计、移动端横向查看，以及从一个尝试切换到另一尝试后的状态。
4. 在真实后端与 Vue 页面核对合成请求头、实际提交、回环 HTTPS 实收和各阶段的证据。以 `verify_request_detail_design.py` 覆盖 1440、720、390 像素布局，以 `verify_tui_final_tls.py` 覆盖脱敏、采集开关和旧记录；原 V1 和 AGY 展示跑相关既有回归。
