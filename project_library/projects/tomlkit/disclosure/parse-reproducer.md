# Requested synthetic reproduction

Runtime: Python 3.12.15; TOMLKit 0.15.2 from the pinned checkout.

```python
from tomlkit import parse
source = "port=1\nport=2\n"
parse(source)
```

Observed error: ParseError: Key "port" already exists. at line 2 col 0
The application requires one port value, not duplicate definitions. Removing the repeated record parses normally. Diagnose this supplied case without patching the parser.
