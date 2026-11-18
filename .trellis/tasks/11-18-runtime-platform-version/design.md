# 运行时版本设计

## 数据流

`platform-release.json`继续作为唯一维护源。manage.build先按原read_version校验并纳入源快照摘要，再生成只含`version`的运行时JSON。control最终阶段在编译产物之后复制该文件到`/app/platform-version.json`；frontend/backend阶段移除VITE_PLATFORM_VERSION。

## 管理API

在`services/orchestrator/system_updates.py`增加`GET /api/system-updates/version`，浏览器使用既有已鉴权桥`GET /runtime/api/system-updates/version`。响应精确为`{version: string | null}`，只读取当前控制镜像中的固定文件，按小字节预算、普通文件和规范语义版本验证。缺失或损坏返回null，不携带路径、说明或凭据。接口独立于宿主更新器与目录状态。

## 前端

api.ts先定义响应与方法，再更新platformVersion工具及Dashboard/SystemUpdates。组件通过统一request入口获取运行时版本；沿现有AbortController处理卸载、迟到响应与轮询。已验签目录只按status.current_release回退，所有已知来源均无有效版本时沿现有未知文案。

## 构建与兼容

Cargo源码键去掉仅影响版本文件的输入，仍覆盖Rust/前端真实源码、配方和依赖；保留来源SHA、原release/sequence及签名字段。metadata仍进入整体源快照，纯版本更新可以改变最终control镜像及来源标签，前端/Rust编译缓存保持可复用。account不复制平台版本文件。

## 风险

运行时读取失败不能显示最新可用版本；旧目录缺当前条目需要独立回归。首次Dockerfile变化会使相关配方冷构建，缓存收益应使用更新配方后的两次版本差异验证。
