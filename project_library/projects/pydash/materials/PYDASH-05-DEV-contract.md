# 多路径客户订单编辑在独立JSON副本中原子提交

路线05：复用Pointer对JSON副本按序执行set/remove/test，成功返回新树、后期失败来源不变，操作value也隔离；不冒充任意对象或并发事务。
