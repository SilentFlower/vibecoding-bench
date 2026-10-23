# 兼容机型候选与来源

## 使用方式

本任务独立定义合成 DMI 模板。以下原厂资料仅核对 CPU 与机型大类的兼容性，不代表已获取真实设备的 SMBIOS／DMI dump，也不能据此捏造原厂 BIOS 版本、真实服务标签、硬件 UUID 或其它机器独有值。

模板注册表在实施中定义明确文本和兼容的现有 CPU 模板 ID，版本字段是注册表的固定显示值；serial、uuid 独立随机生成后固定。模板 ID 只追加，不因资料页面或生成器升级改变已保存内容。

## 已核对候选

| CPU 家族与现有候选 | 可用机型大类 | 原厂依据 |
|---|---|---|
| Naples：EPYC 7301、7351、7401、7451 | Dell PowerEdge R7425 | [Dell 安装与维护手册中的 EPYC 型号表](https://www.dell.com/support/manuals/en-us/poweredge-r7425/per7425_ism/system-memory?guid=guid-94f7f9b9-48a9-436b-b152-882a1e9361b6&lang=en-us) |
| Naples：EPYC 7301、7351、7401、7451 | HPE ProLiant DL385 Gen10 | [HPE 处理器选件列表](https://support.hpe.com/hpesc/public/docDisplay?docId=a00095439en_us&docLocale=en_US&page=GUID-ABDA02C4-C521-4117-AB9E-3183C7619ED1.html)；原厂索引可见对应四种处理器选件，正文页面工具读取为空，不把整份文档记为已完整读取 |
| Cezanne：Ryzen 7 5800H、Ryzen 9 5900HX | Lenovo Legion 7 16ACHg6 | [Lenovo PSREF 产品规格](https://psref.lenovo.com/syspool/Sys/PDF/Legion/Legion_7_16ACHg6/Legion_7_16ACHg6_Spec.html?ver=b420a1b6-e27e-49c9-a61d-742aef047556) |
| Cezanne：Ryzen 7 5800H、Ryzen 9 5900HX | ASUS ROG Strix G15 G513（2021） | [ASUS 原厂规格页](https://rog.asus.com/us/laptops/rog-strix/2021-rog-strix-g15-series/spec/?config=90NR0512-M01620)；本轮依据原厂索引中的两个候选型号，不声称已完整检查所有配置 |

## 实施校验

- CPU 模板 ID 必须来自现有注册表，不把 P 后缀、其它代际或其它架构当作等价型号。
- 候选池限制在当前支持家族；不能为了增加随机组合数量放宽代际和指令能力校验。
- 已有 system_profile 不变，DMI 选择适配它；不会为了选中某个 DMI 模板重新抽取 CPU 或内核。
- 相同机型或厂商可以在不同账号中重复出现；账号独立性由独立随机身份字段保证，不要求公共型号名称唯一。
