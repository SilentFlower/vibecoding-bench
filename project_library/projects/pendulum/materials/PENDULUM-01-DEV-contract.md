# Interval与标准时长相等时遵守缓存键哈希契约

路线01：跨timedelta相等既有语义保留，hash改用同一时长代表；Interval彼此仍按端点/absolute比较，不等对象可合法碰撞，真实dict/set验证。
