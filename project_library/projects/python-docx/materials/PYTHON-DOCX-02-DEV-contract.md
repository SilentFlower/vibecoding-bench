# 写入aware核心时间先归一UTC且保留原秒精度政策

路线02：aware核心时间先astimezone UTC再写Z，正负/半小时偏移和跨日保持瞬间；naive原政策和秒精度保留，核真实ZIP与重开。
