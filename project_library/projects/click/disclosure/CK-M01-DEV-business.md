# Business scope

Implement the complete public note-display enhancement for both base and usage errors. Preserve streams, color, unnoted output, usage, exit codes and format_message. Modify only the authorized implementation and new public test file, with meaningful original-failing tests.

# Investigation topics

- 定位CLI错误附注未显示的边界

# Supplied business material: materials/error-notes.py

import click
from click.testing import CliRunner

@click.command()
def ship():
    """抛出带本地补救信息的合成错误。@return None。"""
    error = click.ClickException("Order unavailable")
    error.add_note("Check local input")
    error.add_note("咖啡\nsecond line")
    raise error

result = CliRunner().invoke(ship)
print(result.exit_code)
print(result.stderr)


# Supplied business material: materials/notes-contract.md

Enhance controlled error display for both ClickException.show and UsageError.show. After the primary error, emit each nonempty __notes__ string in original order, with exactly one "Note: " prefix per note and preserved internal newlines/Unicode. Ignore empty-string notes. Preserve explicit output streams, current echo color handling, exit codes 1/2, usage/help text appearing once, and byte-identical output when no notes are present. Do not add a traceback or alter format_message. Use an absence-safe notes lookup so Python versions without native add_note remain compatible. Only library/src/click/exceptions.py and the new public regression file library/tests/test_exceptions/test_click_exception.py may change. Add meaningful original-failing public tests for both base and usage errors, and preserve the complete frozen original suite and test controls.

