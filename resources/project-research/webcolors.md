# Webcolors：真实项目研究

固定官方 [ubernostrum/webcolors](https://github.com/ubernostrum/webcolors) 的提交 `6c8da6832eb4ae2591a1883a0d1371263d6cd4db`，包元数据版本26.10.0a0。已核对来源、许可、真实源码、原生基线与本地主题清单，形成[二十步研究路线](./webcolors-roadmap-20.md)。路线尚未实施，冻结验收与正式接入未开始。

## 来源、许可与规模

官方仓库页面、完整提交页面和pyproject的Source Code指向一致；根LICENSE为BSD-3-Clause，保留James Bennett及贡献者归属。颜色名称与数值来自HTML/CSS标准，源码已有对应来源；标准内容不因主仓BSD声明而变为原创。研究仅链接WHATWG/W3C规范，不复制规范实现或第三方测试集进入产品。

真实工程39个跟踪文件、204253字节；包括测试和工具的15个Python文件共3016行。运行只依赖Python标准库，独立venv含pytest与coverage共51695258字节，安装12.993秒，实际版本和制品摘要保存于requirements-frozen.txt与installation.json。无需外部服务。

逐个读取公开导出、IntegerRGB/PercentRGB/HTML5SimpleColor、六个源码模块的转换/规范化/名称表及HTML旧式算法，结合原生测试、格式约定和FAQ。FAQ明确建议通过colorsys处理HSL、人工处理alpha；相应路线是本地扩展提案，不能称上游已承诺或现有行为缺陷。

## 真实执行与原生基线

复用同一提交已成功执行的完整默认pytest：**475主测试通过，0失败、0错误、0跳过、0xfail、0xpass**。这是宿主Python3.12.3的独立venv执行，墙钟1.118秒，进程峰RSS31056KiB；原始命令、当轮XML/log均保留，没有重跑或改写为容器测试证据。上游nox的多Python矩阵、coverage合并100%门槛、lint/docs未运行。tests/definitions.py需要联网核对标准，full_colors.py为额外穷举工具，都不属于这次默认pytest通过声明。

补充业务观察在标准账号镜像Python3.12.15、UID1000、256MiB、离线只读容器运行：三个中文主题色名称/短hex/长hex转换为RGB，写临时主题.json并读回逐值一致，导入实际来自/source/src/webcolors。容器无账号HOME或凭据挂载，运行退出0、无OOM，删除已确认；这次场景不能代替475项基线。执行时间以observations-result.json为准。

20条原版观察中确认四项缺陷：CSS4反向能得到rebeccapurple而正向/枚举失败且公共常量缺失，独立HTML旧式入口也错误解释该名称；旧式HTML解析多去掉了非ASCII空白；hex规范化接受结尾换行；十进制负零百分比保留负号。负零仍解码为黑色，未误称RGB数值错误。其余16项是明确的新业务合同；已有名称大小写、gray/grey别名、裁剪、短hex展开、百分比转换和宽容旧HTML算法不重复计数。

## 路线、验收及限制

路线面向主题配置、颜色格式互通、品牌色板、离线报表和兼容迁移。每步包含正常/边界验收、实际源码、原生回归、兼容策略及功能依赖。新增API名称是提案；未因探测某个拟议名称不存在便断言整个功能缺失，判断同时依据完整公开入口、源码与FAQ。

严格输入策略采用新接口，旧裁剪/宽容默认保持；精确百分比采用显式模式，不把旧文档说明的舍入当缺陷。HSL优先复用标准库colorsys，HWB/alpha等按选择并固定的规范实现。对比度仅计算声明的颜色数学量，不以单个比值证明整个界面可访问性。所有流程均不发远程业务请求。

## 证据及复跑

证据根`.deploy/github-100-research/resume-app/webcolors/`保存官方元数据、完整revision、源检出、安装报告/冻结依赖、size.json、原生baseline-tests.log/xml/result、observe.py及20条观察、roadmap-20.json、review-result.json和evidence-sha256.json。

```bash
PYTHONDONTWRITEBYTECODE=1 .deploy/github-100-research/resume-main/control/bin/python .deploy/github-100-research/run_python_probe.py .deploy/github-100-research/resume-app/webcolors --memory 256m
```

跨机器需从官方仓库检出同一完整提交，并按冻结依赖重建环境。原基线命令见baseline-result.json；保留原日志/XML后才能复跑，失败不能读取旧XML。正式接入仍需准备可移植离线依赖、原生调用适配和控制端冻结正反验收。本轮未修改被研究源码、正式内容库，未提交、推送或部署。
