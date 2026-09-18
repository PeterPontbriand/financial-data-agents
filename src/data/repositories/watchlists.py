"""SQLite-backed watchlist repository: create, member/selection edits, reopen.

No provider, network, or analysis work occurs here; only reads/writes against
a caller-owned, already-migrated :class:`SQLiteDatabase`. Conflicts and
missing lookups raise typed errors rather than leaking SQLAlchemy/SQLite
exceptions. Each public method is one short transaction; nothing is left
partially written on failure.
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, delete, func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from src.data.repositories.schema import watchlist_members, watchlist_selections, watchlists
from src.data.repositories.sqlite import SQLiteDatabase
from src.workspace.requests import AnalysisSelection, default_selections
from src.workspace.runs import Watchlist, WatchlistSummary
from src.workspace.watchlists import WatchlistSpec, decode_selection, encode_selection, normalize_ticker


class WatchlistConflictError(ValueError):
    """A watchlist with the same normalized name already exists."""


class WatchlistNotFoundError(ValueError):
    """No watchlist exists with the requested name."""


def _normalize_name(name: str) -> str:
    """Apply the watchlist name comparison convention: trim, then casefold."""
    return name.strip().casefold()


def _utc(value: datetime) -> str:
    """Encode a timezone-aware instant without guessing a missing timezone."""
    if value.utcoffset() is None:
        raise ValueError("Storage timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class SQLiteWatchlistRepository:
    """Persist watchlist aggregates in a borrowed migrated database."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        """Retain a caller-owned database and injected clock/ID generator."""
        self._database = database
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._id_factory = id_factory if id_factory is not None else uuid4

    def create(self, spec: WatchlistSpec) -> Watchlist:
        """Create a watchlist with no members and the contract's default selections.

        Raises:
            ValueError: If ``spec.display_name`` is blank after trimming.
            WatchlistConflictError: If a watchlist with the same normalized
                name already exists.
        """
        watchlist = Watchlist(
            watchlist_id=self._id_factory(),
            display_name=spec.display_name.strip(),
            normalized_name=_normalize_name(spec.display_name),
            created_at=self._clock(),
            members=(),
            selections=default_selections(),
        )
        try:
            with self._database.transaction() as connection:
                connection.execute(
                    watchlists.insert().values(
                        watchlist_id=str(watchlist.watchlist_id),
                        normalized_name=watchlist.normalized_name,
                        display_name=watchlist.display_name,
                        created_at=_utc(watchlist.created_at),
                        updated_at=None,
                    )
                )
                if watchlist.selections:
                    connection.execute(
                        watchlist_selections.insert(),
                        [
                            {
                                "watchlist_id": str(watchlist.watchlist_id),
                                "method_id": selection.method_id,
                                "position": position,
                                "config_schema_version": selection.config_schema_version,
                                "selection_json": encode_selection(selection),
                            }
                            for position, selection in enumerate(watchlist.selections)
                        ],
                    )
        except IntegrityError as exc:
            raise WatchlistConflictError(f"A watchlist named {spec.display_name!r} already exists.") from exc
        return watchlist

    def get(self, name: str) -> Watchlist | None:
        """Return the watchlist matching ``name`` case-insensitively, or None."""
        normalized = _normalize_name(name)
        with self._database.read() as connection:
            watchlist_id = connection.execute(
                select(watchlists.c.watchlist_id).where(watchlists.c.normalized_name == normalized)
            ).scalar_one_or_none()
            if watchlist_id is None:
                return None
            return self._load(connection, watchlist_id)

    def list(self) -> tuple[WatchlistSummary, ...]:
        """Return every watchlist as a summary, ordered by creation then ID."""
        with self._database.read() as connection:
            rows = (
                connection.execute(select(watchlists).order_by(watchlists.c.created_at, watchlists.c.watchlist_id))
                .mappings()
                .all()
            )
            summaries = [
                WatchlistSummary(
                    watchlist_id=UUID(row["watchlist_id"]),
                    display_name=row["display_name"],
                    member_count=self._count(connection, watchlist_members, row["watchlist_id"]),
                    selection_count=self._count(connection, watchlist_selections, row["watchlist_id"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=None if row["updated_at"] is None else datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]
        return tuple(summaries)

    def add_members(self, name: str, tickers: Sequence[str]) -> Watchlist:
        """Append normalized tickers not already present; existing ones are no-ops.

        The whole batch is validated before any row is written, and applied
        in one transaction. Order of newly added tickers follows ``tickers``.

        Raises:
            ValueError: If any ticker normalizes to empty.
            WatchlistNotFoundError: If no watchlist matches ``name``.
        """
        normalized_tickers = [normalize_ticker(ticker) for ticker in tickers]
        with self._database.transaction() as connection:
            watchlist_id = self._find_id(connection, name)
            existing = set(
                connection.execute(
                    select(watchlist_members.c.ticker).where(watchlist_members.c.watchlist_id == watchlist_id)
                ).scalars()
            )
            next_position = self._next_position(connection, watchlist_members, watchlist_id)
            rows: list[dict[str, Any]] = []
            seen = set(existing)
            for ticker in normalized_tickers:
                if ticker in seen:
                    continue
                seen.add(ticker)
                rows.append({"watchlist_id": watchlist_id, "ticker": ticker, "position": next_position})
                next_position += 1
            if rows:
                connection.execute(watchlist_members.insert(), rows)
                self._touch(connection, watchlist_id)
            return self._load(connection, watchlist_id)

    def remove_members(self, name: str, tickers: Sequence[str]) -> Watchlist:
        """Remove normalized tickers if present; absent ones are no-ops.

        Raises:
            ValueError: If any ticker normalizes to empty.
            WatchlistNotFoundError: If no watchlist matches ``name``.
        """
        normalized_tickers = {normalize_ticker(ticker) for ticker in tickers}
        with self._database.transaction() as connection:
            watchlist_id = self._find_id(connection, name)
            if normalized_tickers:
                result = connection.execute(
                    delete(watchlist_members).where(
                        watchlist_members.c.watchlist_id == watchlist_id,
                        watchlist_members.c.ticker.in_(normalized_tickers),
                    )
                )
                if result.rowcount:
                    self._touch(connection, watchlist_id)
            return self._load(connection, watchlist_id)

    def set_selection(self, name: str, selection: AnalysisSelection) -> Watchlist:
        """Add or replace the one selection for ``selection.method_id``.

        A new method is appended after the current highest position; an
        existing method keeps its position and only its configuration changes.

        Raises:
            WatchlistNotFoundError: If no watchlist matches ``name``.
        """
        payload = encode_selection(selection)
        with self._database.transaction() as connection:
            watchlist_id = self._find_id(connection, name)
            existing_position = connection.execute(
                select(watchlist_selections.c.position).where(
                    watchlist_selections.c.watchlist_id == watchlist_id,
                    watchlist_selections.c.method_id == selection.method_id,
                )
            ).scalar_one_or_none()
            if existing_position is None:
                position = self._next_position(connection, watchlist_selections, watchlist_id)
                connection.execute(
                    watchlist_selections.insert().values(
                        watchlist_id=watchlist_id,
                        method_id=selection.method_id,
                        position=position,
                        config_schema_version=selection.config_schema_version,
                        selection_json=payload,
                    )
                )
            else:
                connection.execute(
                    update(watchlist_selections)
                    .where(
                        watchlist_selections.c.watchlist_id == watchlist_id,
                        watchlist_selections.c.method_id == selection.method_id,
                    )
                    .values(config_schema_version=selection.config_schema_version, selection_json=payload)
                )
            self._touch(connection, watchlist_id)
            return self._load(connection, watchlist_id)

    def disable_selection(self, name: str, method_id: str) -> Watchlist:
        """Remove the selection for ``method_id`` if present; absent is a no-op.

        Raises:
            WatchlistNotFoundError: If no watchlist matches ``name``.
        """
        with self._database.transaction() as connection:
            watchlist_id = self._find_id(connection, name)
            result = connection.execute(
                delete(watchlist_selections).where(
                    watchlist_selections.c.watchlist_id == watchlist_id,
                    watchlist_selections.c.method_id == method_id,
                )
            )
            if result.rowcount:
                self._touch(connection, watchlist_id)
            return self._load(connection, watchlist_id)

    def _touch(self, connection: Connection, watchlist_id: str) -> None:
        """Bump ``updated_at`` to the injected clock's current instant."""
        connection.execute(
            update(watchlists).where(watchlists.c.watchlist_id == watchlist_id).values(updated_at=_utc(self._clock()))
        )

    def _find_id(self, connection: Connection, name: str) -> str:
        """Resolve a name to its watchlist ID, or raise if none matches."""
        watchlist_id = connection.execute(
            select(watchlists.c.watchlist_id).where(watchlists.c.normalized_name == _normalize_name(name))
        ).scalar_one_or_none()
        if watchlist_id is None:
            raise WatchlistNotFoundError(f"No watchlist named {name!r} exists.")
        return cast(str, watchlist_id)

    @staticmethod
    def _next_position(connection: Connection, table: Table, watchlist_id: str) -> int:
        """Return one past the current highest position, or zero if empty."""
        highest = connection.execute(
            select(func.max(table.c.position)).where(table.c.watchlist_id == watchlist_id)
        ).scalar_one()
        return 0 if highest is None else cast(int, highest) + 1

    @staticmethod
    def _count(connection: Connection, table: Table, watchlist_id: str) -> int:
        """Return the number of rows in ``table`` for this watchlist."""
        return connection.execute(
            select(func.count()).select_from(table).where(table.c.watchlist_id == watchlist_id)
        ).scalar_one()

    def _load(self, connection: Connection, watchlist_id: str) -> Watchlist:
        """Reconstruct one full watchlist from its three tables in position order."""
        row = connection.execute(select(watchlists).where(watchlists.c.watchlist_id == watchlist_id)).mappings().one()
        members = (
            connection.execute(
                select(watchlist_members.c.ticker)
                .where(watchlist_members.c.watchlist_id == watchlist_id)
                .order_by(watchlist_members.c.position)
            )
            .scalars()
            .all()
        )
        selection_rows = (
            connection.execute(
                select(watchlist_selections)
                .where(watchlist_selections.c.watchlist_id == watchlist_id)
                .order_by(watchlist_selections.c.position)
            )
            .mappings()
            .all()
        )
        selections = tuple(
            decode_selection(row["method_id"], row["config_schema_version"], row["selection_json"])
            for row in selection_rows
        )
        return Watchlist(
            watchlist_id=UUID(row["watchlist_id"]),
            display_name=row["display_name"],
            normalized_name=row["normalized_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=None if row["updated_at"] is None else datetime.fromisoformat(row["updated_at"]),
            members=tuple(members),
            selections=selections,
        )


__all__ = [
    "SQLiteWatchlistRepository",
    "WatchlistConflictError",
    "WatchlistNotFoundError",
]
