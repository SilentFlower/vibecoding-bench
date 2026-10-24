# 日历规则与VTIMEZONE规范接收空格和HTAB折行

路线01：rrulestr与tzical均支持空格/HTAB规范折行，只去一个续行前缀；会议实例和时区offset真实验证，不任意strip业务值。
