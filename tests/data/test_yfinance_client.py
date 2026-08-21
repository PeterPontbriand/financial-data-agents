"""Unit tests for the YFinanceClient quote boundary.

All yfinance access is mocked so no network calls are ever made.
"""

from unittest.mock import patch

import pytest

from src.data.base_client import DataFetchError
from src.data.yfinance_client import YFinanceClient


class TestFetchCurrentPrice:
    """Quote boundary validation and error mapping."""

    def test_valid_quote_returned(self) -> None:
        with patch("src.data.yfinance_client.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info = {"last_price": 151.25}
            assert YFinanceClient().fetch_current_price("TEST") == pytest.approx(151.25)

    @pytest.mark.parametrize(
        "bad_price",
        [0.0, -1.0, float("nan"), float("inf"), float("-inf")],
        ids=["zero", "negative", "nan", "inf", "-inf"],
    )
    def test_non_finite_or_non_positive_quote_rejected(self, bad_price: float) -> None:
        with patch("src.data.yfinance_client.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info = {"last_price": bad_price}
            with pytest.raises(DataFetchError, match="finite and positive"):
                YFinanceClient().fetch_current_price("TEST")

    def test_missing_quote_field_wrapped_as_data_fetch_error(self) -> None:
        with patch("src.data.yfinance_client.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info = {}
            with pytest.raises(DataFetchError, match="Unable to resolve"):
                YFinanceClient().fetch_current_price("TEST")

    def test_provider_lookup_failure_wrapped_as_data_fetch_error(self) -> None:
        with patch("src.data.yfinance_client.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = ConnectionError("simulated network failure")
            with pytest.raises(DataFetchError, match="Unable to resolve"):
                YFinanceClient().fetch_current_price("TEST")
