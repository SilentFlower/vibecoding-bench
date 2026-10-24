# 显式按出现次序拼接重复字段且保留默认兼容政策

路线02：cat显式duplicate_fields=occurrence时字段身份为名字+第n次出现，默认first按原冻结政策不改；联合头保最大重复次数及发现顺序；显式头/短行/missing按同政策，不重复拿首列值。
