# Business scope

Implement the supplied bounded lineage rendering repair and public regression tests. Only the two authorized files may change.

# Investigation topics



# Supplied business material: materials/render-repair.md

A report renders a lineage Node and later exports its source SQL. The pinned Node.to_html inserts exp.Tag into the original source with copy=False,so rendering contaminates SQL with <b> tags and repeated calls can nest highlights. Repair only library/sqlglot/lineage.py and app/test_lineage_render.py. Preserve every original source/expression tree,object identity and parent/arg_key/index relationship. Render a separate representation that still highlights the corresponding expression. Keep repeated labels/titles/edges stable for the same Node,shared sources,an expression that is itself the source,table nodes,dialect and GraphHTML options. Do not disable highlighting,change other APIs or touch original tests/private controls/dependencies. Deliver meaningful public tests that fail on the pinned original and pass after the repair. HTML browser execution and external JavaScript downloads are outside this task.

