"""Shared test helpers for CLI-invoking tests.

CLI error messages rendered through Typer + Rich may contain ANSI escape
sequences (colour, bold, underline) and Rich box/border-drawing characters
(straight and rounded) depending on the terminal environment.  ``normalize_cli_output``
strips both so that tests can assert on the semantic text without coupling
to terminal-styling details.

``isolated_cli_database`` points ``src.cli_support``'s database access at a
disposable, already-migrated SQLite file instead of the real local database
at the default ``database_url``. Momentum and Graham CLI commands call
``ensure_database_ready`` (via ``_production_historical_client`` /
``_production_financial_cache``) before doing any analysis work; without this
isolation, tests that invoke those commands implicitly depend on the
developer machine's real local database already being upgraded to the
current schema head, which breaks after every migration until someone runs
that upgrade by hand.
"""

import re
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from src.config import ProjectSettings

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def normalize_cli_output(output: str) -> str:
    """Strip ANSI terminal-control sequences and normalize Rich box/border layout.

    This makes substring assertions robust across local execution, Windows
    terminals, and headless CI runners where Typer/Rich may or may not emit
    styling codes.  Handles both straight (│┌┐└┘) and rounded (╭╮╰╯)
    border-drawing characters.
    """
    text = _ANSI_ESCAPE_RE.sub("", output)
    for ch in "─│┌┐└┘╭╮╰╯":
        text = text.replace(ch, " ")
    return " ".join(text.split())


@pytest.fixture(autouse=True)
def isolated_cli_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Migrate a disposable database to head and point CLI storage at it.

    Importing this fixture's name into a test module activates it for every
    test in that module, matching pytest's usual cross-module fixture sharing.
    """
    url = f"sqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}"
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    monkeypatch.setattr("src.cli_support.settings", ProjectSettings(database_url=url))
