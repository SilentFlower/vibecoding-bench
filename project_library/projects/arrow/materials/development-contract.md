# Fixed-offset timezone parsing contract

Configuration values must not be silently truncated: `+03:00.34`, `+03:99`, `+24:00`, `+030`, `+03:` and trailing whitespace/text on a bare offset are invalid string expressions and must raise ParserError, not a raw timezone/ZoneInfo ValueError.

Supported bare forms remain `HH`, `+HH`, `-HH`, `HHMM`, `+HHMM`, `-HHMM`, and colon equivalents. Exactly two ASCII digits are required per component, hours are 00..23 and minutes 00..59; signed zero is UTC-equivalent. No implicit whitespace stripping.

Retain existing `local`, `utc`, `UTC`, `Z` and valid IANA names. For legacy `(UTC` wrappers, accept the same valid offset followed by either end of input (existing unclosed form), `)`, or `)` plus an ASCII space and a nonempty descriptive label. The label is opaque text; do not parse its city names. Reject repeated/malformed wrappers, missing offsets, suffixes before the closing parenthesis and `)junk` without the separating space. Empty strings and invalid IANA names raise ParserError. Non-string inputs are outside this string contract.

Modify `library/arrow/parser.py` and add public tests in `library/tests/test_development_timezone_parser.py`. Keep the original parser/factory suite and test controls unchanged. No additional dependencies or timezone network access.
