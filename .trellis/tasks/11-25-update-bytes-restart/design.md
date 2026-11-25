# 技术设计

沿 SystemUpdateHost.prepare 的镜像拉取引入 Docker Engine 的结构化分层进度，保留鉴权、digest 固定、标签校验与回退。按组件、层和尝试更新实际计数，处理共享层、缓存与重新拉取。只在分母可验证时计算百分比，标明其对应当前下载单位。签名清单 unpacked_bytes 为解包大小，不作网络分母。离线包用现有流式已读字节及 bundle.size。将脱敏、节流的可选字段沿原更新操作暴露给 SystemUpdateOperation；并发进度更新不能覆盖取消或终态。SystemUpdateDialog.vue 在进度页复用对应回执的安装动作与原重启提示，兼容旧宿主及旧操作。
