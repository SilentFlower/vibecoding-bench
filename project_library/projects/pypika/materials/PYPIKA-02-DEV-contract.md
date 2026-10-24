# EXISTS与NOT EXISTS报表投影保持别名并隔离条件上下文

路线02：EXISTS/NOT EXISTS投影使用外层别名且关闭内部别名意图，WHERE不带输出列别名；SQLite内存执行证明真实结果列身份。
