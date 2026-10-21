# Requested synthetic incident

The attached loader.py is the complete invocation. The synthetic file is the exact text `{not-json`. The complete exception is json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1), raised by json.loads(target.read_text()). Recorded application events: one load call, no sleep calls. The exact predicate is retry_if_exception_type(FileNotFoundError), with three total attempts and reraise=True. This file is never production configuration. Diagnose only the disclosed case.
