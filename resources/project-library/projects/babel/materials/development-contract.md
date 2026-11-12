# Explicit-pattern datetime parts

Reports need to style a month, weekday, or timezone without searching or splitting a localized string. Add `babel.dates.format_datetime_to_parts(datetime=None, format="yyyy-MM-dd", tzinfo=None, locale=None)` using the real locale-aware date/time implementation.

The result is a fresh list of dictionaries in source-token order, with exactly these keys:

* A field: `{"type": "M", "field": "MMMM", "value": "April"}`. type is the original one-character LDML field symbol; field preserves its exact repetition; value is the localized rendered text as a string.
* Literal text: `{"type": "literal", "field": null, "value": " / "}`. Preserve Babel's existing tokenization boundaries, apostrophe escaping and non-ASCII literals. Do not emit an empty literal for the empty pattern.

This first delivery accepts explicit LDML pattern strings only. Named predefined formats `short`, `medium`, `long`, `full` raise ValueError; non-string patterns raise TypeError. Other unsupported fields/widths and unmatched quoting follow the existing parse_pattern/format_datetime behavior. An empty pattern returns []. Repeated fields remain separate tokens. Every accepted explicit pattern must satisfy `"".join(part["value"] for part in parts) == format_datetime(instant, pattern, tzinfo, locale)`.

Use exactly the same instant normalization (including date/timestamp/naive handling), locale resolution and timezone conversion as format_datetime; support numeric/text months, weekday, date/time, day period, fractional seconds and timezone fields through the existing formatter. Preserve escaped percent signs and quotes as literal text. Returned containers must not be cached or shared between calls. Do not embed HTML, parse rendered output to rediscover fields, or alter existing string APIs and locale data.

Modify only `library/babel/dates.py`; deliver meaningful original-failing tests at `library/tests/test_development_datetime_parts.py`. Existing full upstream tests and controls are frozen. No dependency or locale-data changes.
