Complete YAML: base: &stock [A]
left: *stock
right: *stock
. Check identity, appendB through left, and observe right. Separately parse the bounded literal &stock [*stock] and check identity only. Explain graph ownership and how application mutation/traversal differs from assuming independent JSON trees. Never expand or JSON-serialize an unbounded graph. No edits.
