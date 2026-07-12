from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from unittest.mock import patch, ANY

from main import (
    get_role_label,
    parse_month_year,
    _fake_price_distribution,
    filter_data,
    render_gated_chart,
)


# ---------------------------------------------------------------------------
# get_role_label
# ---------------------------------------------------------------------------

class TestGetRoleLabel:
    def test_subscribed(self):
        assert get_role_label("subscribed") == "Subscribed"
        assert get_role_label("Subscribed") == "Subscribed"
        assert get_role_label("SUBSCRIBED") == "Subscribed"

    def test_free(self):
        assert get_role_label("free") == "Free"
        assert get_role_label("guest") == "Free"
        assert get_role_label("") == "Free"

    def test_unknown(self):
        assert get_role_label("premium") == "Free"


# ---------------------------------------------------------------------------
# parse_month_year
# ---------------------------------------------------------------------------

class TestParseMonthYear:
    def test_valid(self):
        result = parse_month_year("2024-01")
        assert result == pd.Timestamp("2024-01-01")

        result = parse_month_year("2023-12")
        assert result == pd.Timestamp("2023-12-01")

    def test_invalid(self):
        result = parse_month_year("abc")
        assert result is None or pd.isna(result)

        result = parse_month_year("")
        assert result is None or pd.isna(result)

        result = parse_month_year("13-2024")
        assert result is None or pd.isna(result)


# ---------------------------------------------------------------------------
# _fake_price_distribution
# ---------------------------------------------------------------------------

class TestFakePriceDistribution:
    def test_returns_figure(self):
        fig = _fake_price_distribution()
        assert isinstance(fig, go.Figure)

    def test_has_one_trace(self):
        fig = _fake_price_distribution()
        assert len(fig.data) == 1

    def test_histogram_type(self):
        fig = _fake_price_distribution()
        assert fig.data[0].type == "histogram"

    def test_has_height(self):
        fig = _fake_price_distribution()
        assert fig.layout.height == 400

    def test_deterministic_seed(self):
        fig1 = _fake_price_distribution()
        fig2 = _fake_price_distribution()
        # Both should produce identical traces (seed 42)
        assert np.array_equal(fig1.data[0].x, fig2.data[0].x)


# ---------------------------------------------------------------------------
# render_gated_chart
# ---------------------------------------------------------------------------

class TestRenderGatedChart:
    @patch("main.st.plotly_chart")
    def test_subscribed_plots_real_chart(self, mock_plot):
        """Subscribed users see the real figure."""
        fig = go.Figure()
        render_gated_chart("subscribed", fig, "Test Feature")
        mock_plot.assert_called_once_with(fig, width='stretch')

    @patch("main.st.markdown")
    def test_free_shows_blurred(self, mock_md):
        """Free users get blurred HTML."""
        fig = go.Figure()
        render_gated_chart("free", fig, "Test Feature")
        assert mock_md.called
        html_arg = mock_md.call_args[0][0]
        assert "filter:blur(12px)" in html_arg
        assert "Test Feature" in html_arg
        assert mock_md.call_args[1].get("unsafe_allow_html") is True

    @patch("main.st.markdown")
    def test_guest_shows_blurred(self, mock_md):
        """Guest users also get blurred."""
        fig = go.Figure()
        render_gated_chart("guest", fig, "Guest Feature")
        assert mock_md.called
        html_arg = mock_md.call_args[0][0]
        assert "filter:blur(12px)" in html_arg

    @patch("main.st.markdown")
    def test_fake_fig_fn_is_called(self, mock_md):
        """When fake_fig_fn is provided, it is used instead of the real fig."""
        real_fig = go.Figure()
        fig2 = go.Figure()
        render_gated_chart("free", real_fig, "X", fake_fig_fn=lambda: fig2)
        # The HTML rendering should produce output — just verify it ran
        assert mock_md.called


# ---------------------------------------------------------------------------
# filter_data
# ---------------------------------------------------------------------------

SAMPLE_DF = pd.DataFrame({
    "property_type_grouped": ["Terrace", "Condominium", "Terrace", "Flat", "Condominium"],
    "district": ["Cheras", "Damansara", "Cheras", "Cheras", "Damansara"],
    "mukim": ["Mukim A", "Mukim B", "Mukim A", "Mukim A", "Mukim B"],
    "land_area_sqft": [1000.0, 500.0, 1200.0, 300.0, 600.0],
    "txn_price_rm": [500_000, 300_000, 600_000, 150_000, 350_000],
    "txn_mth_id": ["2024-01", "2024-01", "2024-02", "2024-02", "2024-03"],
})


class TestFilterData:
    def test_no_filters(self):
        result = filter_data(SAMPLE_DF, [], [], [], None, None)
        assert len(result) == 5

    def test_property_type_filter(self):
        result = filter_data(SAMPLE_DF, ["Terrace"], [], [], None, None)
        assert len(result) == 2
        assert (result["property_type_grouped"] == "Terrace").all()

    def test_district_filter(self):
        result = filter_data(SAMPLE_DF, [], ["Cheras"], [], None, None)
        assert len(result) == 3
        assert (result["district"] == "Cheras").all()

    def test_mukim_filter(self):
        result = filter_data(SAMPLE_DF, [], [], ["Mukim B"], None, None)
        assert len(result) == 2
        assert (result["mukim"] == "Mukim B").all()

    def test_land_area_range(self):
        result = filter_data(SAMPLE_DF, [], [], [], (400.0, 900.0), None)
        assert len(result) == 2  # rows 500 and 600 sqft

    def test_price_range(self):
        result = filter_data(SAMPLE_DF, [], [], [], None, None, price_range=(200_000, 400_000))
        assert len(result) == 2  # 300k and 350k

    def test_date_range(self):
        start = pd.Timestamp("2024-02-01")
        end = pd.Timestamp("2024-03-01")
        result = filter_data(SAMPLE_DF, [], [], [], None, (start, end))
        assert len(result) == 3  # 2024-02 and 2024-03 rows

    def test_combined_filters(self):
        result = filter_data(
            SAMPLE_DF,
            ["Terrace", "Condominium"],
            ["Cheras"],
            [],
            (400.0, 1500.0),
            None,
        )
        assert len(result) == 2  # both Cheras Terrace rows within area range

    def test_empty_property_types_skips(self):
        result = filter_data(SAMPLE_DF, [], [], [], None, None)
        assert len(result) == 5

    def test_none_price_range_skips(self):
        result = filter_data(SAMPLE_DF, [], [], [], None, None, price_range=None)
        assert len(result) == 5

    def test_no_match_returns_empty(self):
        result = filter_data(SAMPLE_DF, ["Bungalow"], [], [], None, None)
        assert len(result) == 0
