# Business scope

Implement only the explicitly authorized filtered-delete repair and public regressions in the supplied material. Preserve original tests and all listed compatibility boundaries.

# Investigation topics

- 区分已有路径批改和字面新建
- 解释列表删除留空位及无匹配错误

# Supplied business material: materials/write.md

On{orders:[{state:old},{state:old}]}run set("orders/*/state","new"),then set("missing/name","value"). On a fresh{}run new("literal*/0/id","A"). Compare counts,created shape,returned identity and actual glob/literal semantics. No project files may change and no unbounded user index is authorized.


# Supplied business material: materials/delete.md

Synthetic object{xs:[A,B,C]};delete xs/1,then xs/2,and separately delete missing. Observe exact list content and exception behavior; retained item indexes must not be silently reinterpreted. No real data or project edits are authorized for this explanation.


# Supplied business material: materials/delete-repair.md

Explicit repair authorization: modify only library/dpath/__init__.py and add app/test_delete_filter.py. Reproduction: value={selected:{drop:1,keep:0},outside:{same:1}};delete(value,"selected/*",afilter=lambda item:item==1). Pinned original deletes2 including outside.same. Required result deletes only selected.drop,count1,and preserves outside.same. With a filter, require both a glob match and a matching leaf value; no effective match still raises existing PathNotFound. Preserve unfiltered glob behavior,custom separators,list deletion/index handling,public signatures,all original tests and other APIs. Add meaningful public unittest regressions failing on original and passing after repair. No broader merge/search/API change or real deletion is authorized.

