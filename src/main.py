"""Main entry point for the Financial Data Agents analyzer."""

from src.utils.logger_util import setup_global_logging


def main() -> None:
    """Entry point for the Financial Data Agents analyzer."""
    setup_global_logging()

    # Delayed import to avoid circular dependency trees
    from src.cli import app

    app()


if __name__ == "__main__":
    main()
