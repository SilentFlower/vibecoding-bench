# 商品工具用法

```bash
python shop.py product 咖啡 --quantity 3
python shop.py export catalog.json --output result.json
```

导出保留输入顺序，仅输出 sku、name、quantity，UTF-8 中文直接保存。输入必须是对象数组，每个 sku、name 是非空字符串，quantity 是非负整数且不能是布尔值，sku 不可重复；空数组允许。

所有记录校验后才创建输出。无效输入、缺失输入、同路径或已有输出都失败且不修改输入，不覆盖已有输出。输出 JSON 的缩进不是业务契约。这里是验证端参考材料，不投放给受评模型。
