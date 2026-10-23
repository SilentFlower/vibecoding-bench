"""公开复现JSON预览污染共享深度。"""
from anytree import Node
from anytree.exporter import DictExporter, JsonExporter
root = Node('catalog')
Node('product',parent=root)
shared = DictExporter()
print('before',shared.maxlevel,shared.export(root))
print('preview',JsonExporter(shared,maxlevel=1).export(root))
print('after',shared.maxlevel,shared.export(root))
