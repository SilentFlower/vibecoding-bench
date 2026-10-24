# 非法显式标量通过带源位置YAML构造错误统一报告

路线02：仅内建bool/int/float/timestamp预期转换错误规范为ConstructorError并保位置/cause；timestamp无匹配先检查，合法值不改，不吞任意内部或用户构造器错误。
