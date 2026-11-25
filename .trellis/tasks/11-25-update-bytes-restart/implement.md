# 实施与验证

1. 逐项核对 system_update_host.py 的 prepare 与 _load_release_bundle、system_updater.py 的 _execute/_public_operation、前端 SystemUpdateOperation 及 SystemUpdateDialog.vue。
2. 用可分段放行的本地镜像和包对照实际接收字节，测并行层、缓存、未知大小、重试、断流回退、解包和校验。正常镜像路径应有可计算的百分比。
3. 浏览器从下载一路点到同页立即重启。验证回执过期、重开、双击、旧宿主及不支持快速重启的兼容安装。
4. 在 deploy/flower2api 运行 python -m unittest test_system_host test_system_updater test_system_workflow；运行 Web 生产构建、verify_system_update_browser.py 对应场景，验证固定宿主更新器打包可用。
