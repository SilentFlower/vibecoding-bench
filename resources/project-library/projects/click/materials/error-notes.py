import click
from click.testing import CliRunner

@click.command()
def ship():
    """Raise a synthetic error with local remediation notes. @return None."""
    error = click.ClickException("Order unavailable")
    error.add_note("Check local input")
    error.add_note("咖啡\nsecond line")
    raise error

result = CliRunner().invoke(ship)
print(result.exit_code)
print(result.stderr)
