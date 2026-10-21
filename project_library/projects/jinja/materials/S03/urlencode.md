# Mapping query encoding
Pinned source reproduction:
from collections import UserDict
from jinja2.filters import do_urlencode
do_urlencode({'Aa': 'A+1'}) == 'Aa=A%2B1'
do_urlencode(UserDict({'Aa': 'A+1'})) == 'A=a'
A UserDict with the one-character key 'q' raises ValueError. Pair iterables may have duplicate keys, and string inputs represent paths whose slash quoting behavior must stay unchanged. The diagnosis concerns this frozen original reproduction even if later tasks accept code changes.
