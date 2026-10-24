# 排班导出正确投影单列、零列与任意标识变量顺序

路线03：显式order统一按所选变量投影，单列返回一元tuple、空order返回每解空tuple；None保留旧默认。未知/重复/字符串含糊order预先拒绝，任意hashable身份可用，投影导致重复时原ListDict验证仍明确报错。
