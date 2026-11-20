# 节点目标镜像完整性设计

以 `NodeDeployment.prefetch_images` 和 `_ensure_image` 为共享交付入口。以中央已校验的目标记录为来源，核对目标的实际平台、角色、发布标签和配置归属。Docker 索引 ID 可在内容缺失时仍被查询到，只有通过完整性验收的镜像可作为预取完成回执。

同名引用已归属该目标但内容残缺时，通过既有固定身份 SSH 通道从中央流式补齐。按 Docker API 能力及隔离实验验证选定平台的 save/load 方式，并保留已验证的旧版单平台入口。导入完成后重读实际镜像并校验，沿原同名冲突保护处理校验到的真实差异。

两类镜像准备证据应在节点排空和停止前收齐。复用原中央门禁、节点操作锁、镜像传输暂停点、健康检查和回退。失败摘要记录稳定的阶段与原因分类。

参考 [Docker Engine API 版本历史](https://docs.docker.com/reference/api/engine/version-history/) 和 [镜像导出](https://docs.docker.com/reference/cli/docker/image/save/)。
