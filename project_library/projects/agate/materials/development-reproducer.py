"""公开复现索引键异常和等值右列被错误省略。"""
import agate
left = agate.Table([('A','N')], ['id','zone'], [agate.Text(),agate.Text()])
right = agate.Table([('A','N','ok')], ['key','area','label'], [agate.Text()]*3)
try:
    print(left.join(right,[0,1],[0,1]).column_names)
except ValueError as error:
    print(type(error).__name__, str(error))
right = agate.Table([('A','A')], ['copy','key'], [agate.Text()]*2)
print(left.join(right,'id','key').column_names)
