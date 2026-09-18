"""Verify watchlist create/edit/idempotence/conflict/order/reopen through SQLite."""

import socket
from collections.abc import Generator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import select

from alembic import command
from src.config import ProjectSettings
from src.data.repositories.schema import watchlist_members, watchlist_selections, watchlists
from src.data.repositories.sqlite import SQLiteDatabase
from src.data.repositories.watchlists import SQLiteWatchlistRepository, WatchlistConflictError, WatchlistNotFoundError
from src.workspace.requests import GrahamGrowthSelection, GrahamNumberSelection, default_selections
from src.workspace.watchlists import WatchlistSpec

NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 18, 12, 5, 0, tzinfo=UTC)
FIRST_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture(autouse=True)
def mock_momentum_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Materialize deterministic Momentum defaults for ``default_selections()``."""
    with monkeypatch.context() as ctx:
        ctx.setattr(
            "src.config.ProjectSettings.get_momentum_analysis",
            lambda self: {"window_sizes": {"short_window": 2, "long_window": 5}},  # noqa: ARG005
        )
        yield


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SQLiteDatabase]:
    url = f"sqlite:///{(tmp_path / 'watchlists.sqlite3').as_posix()}"
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    database = SQLiteDatabase(ProjectSettings(database_url=url))
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def repository(database: SQLiteDatabase) -> SQLiteWatchlistRepository:
    ids = iter([FIRST_ID, SECOND_ID])
    return SQLiteWatchlistRepository(database, clock=lambda: NOW, id_factory=lambda: next(ids))


def test_create_materializes_no_members_and_default_selections(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="  Dividend Growth  "))
    assert watchlist.watchlist_id == FIRST_ID
    assert watchlist.display_name == "Dividend Growth"
    assert watchlist.normalized_name == "dividend growth"
    assert watchlist.created_at == NOW
    assert watchlist.updated_at is None
    assert watchlist.members == ()
    assert [selection.method_id for selection in watchlist.selections] == [
        "sma_crossover",
        "graham_number",
        "reported_fcf_eps_cagr",
    ]
    assert watchlist.selections == default_selections()


def test_create_rejects_blank_display_name(repository: SQLiteWatchlistRepository) -> None:
    with pytest.raises(ValueError, match="blank"):
        repository.create(WatchlistSpec(display_name="   "))


def test_touch_rejects_a_naive_clock(database: SQLiteDatabase) -> None:
    aware_repository = SQLiteWatchlistRepository(database, clock=lambda: NOW, id_factory=lambda: FIRST_ID)
    watchlist = aware_repository.create(WatchlistSpec(display_name="Watch"))
    naive_clock = lambda: datetime(2026, 9, 18, 12, 5, 0)  # noqa: E731
    naive_repository = SQLiteWatchlistRepository(database, clock=naive_clock)
    with pytest.raises(ValueError, match="timezone-aware"):
        naive_repository.add_members(watchlist.display_name, ["KO"])


def test_create_duplicate_name_is_a_conflict_and_leaves_storage_unchanged(
    database: SQLiteDatabase, repository: SQLiteWatchlistRepository
) -> None:
    repository.create(WatchlistSpec(display_name="Dividend Growth"))
    with pytest.raises(WatchlistConflictError, match="already exists"):
        repository.create(WatchlistSpec(display_name="  dividend growth  "))
    with database.read() as connection:
        rows = connection.execute(select(watchlists)).all()
        assert len(rows) == 1
        selection_rows = connection.execute(select(watchlist_selections)).all()
        assert len(selection_rows) == 3


def test_get_is_case_and_whitespace_insensitive(repository: SQLiteWatchlistRepository) -> None:
    repository.create(WatchlistSpec(display_name="Dividend Growth"))
    assert repository.get("  DIVIDEND growth ") is not None
    assert repository.get("nonexistent") is None


def test_list_orders_by_creation_and_reports_counts(repository: SQLiteWatchlistRepository) -> None:
    repository.create(WatchlistSpec(display_name="Second"))
    first = repository.create(WatchlistSpec(display_name="First"))
    repository.add_members(first.display_name, ["KO", "PFE"])
    summaries = repository.list()
    assert [summary.display_name for summary in summaries] == ["Second", "First"]
    assert summaries[1].member_count == 2
    assert summaries[1].selection_count == 3


def test_add_members_preserves_order_and_is_idempotent(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    updated = repository.add_members(watchlist.display_name, [" ko ", "pfe", "ko"])
    assert updated.members == ("KO", "PFE")
    again = repository.add_members(watchlist.display_name, ["PFE", "aapl"])
    assert again.members == ("KO", "PFE", "AAPL")


def test_add_members_validates_before_writing_anything(
    database: SQLiteDatabase, repository: SQLiteWatchlistRepository
) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    with pytest.raises(ValueError, match="must not be empty"):
        repository.add_members(watchlist.display_name, ["KO", "   "])
    with database.read() as connection:
        assert connection.execute(select(watchlist_members)).all() == []


def test_add_members_missing_watchlist_raises(repository: SQLiteWatchlistRepository) -> None:
    with pytest.raises(WatchlistNotFoundError):
        repository.add_members("nonexistent", ["KO"])


def test_add_members_with_empty_sequence_is_a_no_op(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    unchanged = repository.add_members(watchlist.display_name, [])
    assert unchanged.members == ()
    assert unchanged.updated_at is None


def test_remove_members_is_idempotent_for_absent_tickers(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    repository.add_members(watchlist.display_name, ["KO", "PFE", "AAPL"])
    updated = repository.remove_members(watchlist.display_name, ["PFE", "NOTHERE"])
    assert updated.members == ("KO", "AAPL")
    again = repository.remove_members(watchlist.display_name, ["PFE"])
    assert again.members == ("KO", "AAPL")


def test_remove_members_missing_watchlist_raises(repository: SQLiteWatchlistRepository) -> None:
    with pytest.raises(WatchlistNotFoundError):
        repository.remove_members("nonexistent", ["KO"])


def test_remove_members_with_empty_sequence_is_a_no_op(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    repository.add_members(watchlist.display_name, ["KO"])
    unchanged = repository.remove_members(watchlist.display_name, [])
    assert unchanged.members == ("KO",)


def test_set_selection_replaces_config_and_keeps_position(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    replaced = repository.set_selection(watchlist.display_name, GrahamNumberSelection(bvps_override=12.5))
    positions = [selection.method_id for selection in replaced.selections]
    assert positions == ["sma_crossover", "graham_number", "reported_fcf_eps_cagr"]
    graham_number = next(s for s in replaced.selections if s.method_id == "graham_number")
    assert isinstance(graham_number, GrahamNumberSelection)
    assert graham_number.bvps_override == 12.5


def test_set_selection_appends_a_new_method_after_existing_positions(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    updated = repository.set_selection(
        watchlist.display_name, GrahamGrowthSelection(expected_growth=5.0, aaa_yield_override=4.5)
    )
    assert [selection.method_id for selection in updated.selections] == [
        "sma_crossover",
        "graham_number",
        "reported_fcf_eps_cagr",
        "graham_growth_value",
    ]


def test_set_selection_missing_watchlist_raises(repository: SQLiteWatchlistRepository) -> None:
    with pytest.raises(WatchlistNotFoundError):
        repository.set_selection("nonexistent", GrahamNumberSelection())


def test_disable_selection_is_idempotent_for_absent_method(repository: SQLiteWatchlistRepository) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    updated = repository.disable_selection(watchlist.display_name, "graham_growth_value")
    assert [selection.method_id for selection in updated.selections] == [
        "sma_crossover",
        "graham_number",
        "reported_fcf_eps_cagr",
    ]
    reduced = repository.disable_selection(watchlist.display_name, "graham_number")
    assert [selection.method_id for selection in reduced.selections] == ["sma_crossover", "reported_fcf_eps_cagr"]
    again = repository.disable_selection(watchlist.display_name, "graham_number")
    assert [selection.method_id for selection in again.selections] == ["sma_crossover", "reported_fcf_eps_cagr"]


def test_disable_selection_missing_watchlist_raises(repository: SQLiteWatchlistRepository) -> None:
    with pytest.raises(WatchlistNotFoundError):
        repository.disable_selection("nonexistent", "graham_number")


def test_mutations_bump_updated_at_only_when_something_changes(
    database: SQLiteDatabase, repository: SQLiteWatchlistRepository
) -> None:
    watchlist = repository.create(WatchlistSpec(display_name="Watch"))
    assert watchlist.updated_at is None
    clocked = SQLiteWatchlistRepository(database, clock=lambda: LATER, id_factory=lambda: SECOND_ID)
    unchanged = clocked.remove_members(watchlist.display_name, ["NOTHERE"])
    assert unchanged.updated_at is None
    changed = clocked.add_members(watchlist.display_name, ["KO"])
    assert changed.updated_at == LATER


def test_reopen_preserves_full_watchlist_state(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'reopen.sqlite3').as_posix()}"
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")

    first_database = SQLiteDatabase(ProjectSettings(database_url=url))
    try:
        repository = SQLiteWatchlistRepository(first_database, clock=lambda: NOW, id_factory=lambda: FIRST_ID)
        created = repository.create(WatchlistSpec(display_name="Persisted"))
        repository.add_members(created.display_name, ["KO", "PFE"])
        repository.set_selection(created.display_name, GrahamNumberSelection(bvps_override=9.0))
    finally:
        first_database.close()

    second_database = SQLiteDatabase(ProjectSettings(database_url=url))
    try:
        reopened = SQLiteWatchlistRepository(second_database).get("persisted")
        assert reopened is not None
        assert reopened.watchlist_id == FIRST_ID
        assert reopened.members == ("KO", "PFE")
        graham_number = next(s for s in reopened.selections if s.method_id == "graham_number")
        assert isinstance(graham_number, GrahamNumberSelection)
        assert graham_number.bvps_override == 9.0
    finally:
        second_database.close()


def test_no_network_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Watchlist repository must not access the network.")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    url = f"sqlite:///{(tmp_path / 'offline.sqlite3').as_posix()}"
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    database = SQLiteDatabase(ProjectSettings(database_url=url))
    try:
        repository = SQLiteWatchlistRepository(database, clock=lambda: NOW, id_factory=lambda: FIRST_ID)
        watchlist = repository.create(WatchlistSpec(display_name="Offline"))
        repository.add_members(watchlist.display_name, ["KO"])
        repository.set_selection(watchlist.display_name, GrahamNumberSelection())
        repository.list()
        assert repository.get("offline") is not None
    finally:
        database.close()
