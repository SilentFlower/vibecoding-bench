# 环境变量布尔覆盖使用明确真值且保留显式调用优先级

路线17：内建envwrap对实际bool/Optional[bool]注解、bool默认和显式types回退采用明确真假文字，空/未知值报含参数名错误；直接调用仍优先，字符串False仍字符串，其余类型推断和可选外部provider不改。
