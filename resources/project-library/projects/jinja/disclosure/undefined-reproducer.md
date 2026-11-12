# Supplied incident evidence
The application constructs Environment() and renders the exact template {{ account.name }} with render() and no arguments. The input context is {}.
Complete exception: jinja2.exceptions.UndefinedError: 'account' is undefined
Reproduction:
from jinja2 import Environment
Environment().from_string('{{ account.name }}').render()
Expected business name after supplying account={'name':'研发'}: 研发.
This is now all required material; diagnose the supplied call rather than indefinitely asking for more.
