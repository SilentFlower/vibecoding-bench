# 打包与构建对照

- `codex-proxy-rs` 把前端构建和二进制编译放到独立作业，最终镜像从已构建产物装箱。二进制单独使用 Rust 缓存，最终镜像另用 BuildKit 缓存。 [分作业构建](https://github.com/zyycn/codex-proxy-rs/blob/6420d86aa6d046d5e61205d3772e0a65926df9cf/.github/workflows/_container.yml#L19-L60) [产物装箱](https://github.com/zyycn/codex-proxy-rs/blob/6420d86aa6d046d5e61205d3772e0a65926df9cf/deploy/Dockerfile#L86-L95)
- Flower2API v1.24.0 的同源构建里，两镜像构建耗时 6 分 38 秒，镜像内 AGY 验收耗时 2 分 49 秒，候选压缩归档导出耗时 53 秒，上传耗时 9 秒。发布器已复用同提交的候选镜像，压缩包上传在这一批的占比较小。 [构建运行](https://github.com/SilentFlower/vibecoding-bench/actions/runs/44661667006)
- 优先评估把相同提交的 Vue 产物、Linux Bookworm 网关及发送器二进制作为受信构建产物，供 control 和 account 最终镜像装箱。现有 `RustEmbed` 在编译网关时消费前端产物，所以网关编译需先取得同一提交的 dist。双方共享的 Rust 编译仍执行一次。现有镜像验收、历史数据库演练、签名和镜像摘要继续校验最终装箱结果。 [现有前端及 Rust 阶段](../../../../images/v3/Dockerfile#L16-L31)
- 以同一次提交的冷缓存和热缓存各跑一组原路径与产物装箱路径。对比从构建开始到可信候选可用的总时间，并分别记录编译、导出、上传、候选导入和最终发布。只有总时间改善才改变发版流水线。
