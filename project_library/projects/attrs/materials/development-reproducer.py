"""公开复现跨模型等值字段被误选。"""
import attr
from attr.filters import include, exclude
A = attr.make_class('A', {'x':attr.ib()})
B = attr.make_class('B', {'x':attr.ib()})
selected,foreign = attr.fields(A).x,attr.fields(B).x
print('equal',selected == foreign,'identical',selected is foreign)
print('included',attr.asdict(B(5),filter=include(selected)))
print('excluded',attr.asdict(B(5),filter=exclude(selected)))
