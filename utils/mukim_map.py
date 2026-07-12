import json
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def _load_kl_geojson():
    """Load the official KL GeoJSON file from Malaysia DOSM."""
    geojson_path = os.path.join(os.path.dirname(__file__), "..", "geo_data", "kl_mukims_official.geojson")
    with open(geojson_path, "r") as f:
        return json.load(f)


def _normalize_mukim_name(value: str) -> str:
    return str(value).strip() if pd.notna(value) else "Unknown"


def _build_mukim_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Create a mukim-level summary for the KL choropleth map."""
    summary = df.copy()
    summary["mukim_name"] = summary["mukim"].apply(_normalize_mukim_name)
    summary["txn_price_per_sqft"] = pd.to_numeric(summary["txn_price_per_sqft"], errors="coerce")

    # Group by mukim and aggregate
    grouped = (
        summary.groupby("mukim_name", dropna=False, sort=True)
        .agg(
            transactions=("mukim_name", "size"),
            median_price_per_sqft=("txn_price_per_sqft", "median"),
            avg_price_per_sqft=("txn_price_per_sqft", "mean"),
            property_types=("property_type_grouped", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
        )
        .reset_index()
    )

    # Rename for GeoJSON matching (match official district names)
    grouped = grouped.rename(columns={"mukim_name": "name"})
    return grouped


def render_mukim_map(df: pd.DataFrame, role: str = "free") -> None:
    """Render the KL mukim choropleth heatmap and a property-type selection summary."""
    if df.empty:
        st.info("No data available for the selected filters.")
        return

    property_options = ["All property types"] + sorted(df["property_type_grouped"].dropna().astype(str).unique().tolist())
    selected_group = st.selectbox(
        "Select property type to inspect on the map",
        options=property_options,
        help="Choose a category such as Terrace, Condominium/Apartment, Flat, or view all property types.",
    )

    filtered = df.copy()
    if selected_group != "All property types":
        filtered = filtered[filtered["property_type_grouped"].astype(str) == selected_group]

    summary = _build_mukim_summary(filtered)
    summary = summary.sort_values("median_price_per_sqft", ascending=False)

    # Load official GeoJSON (Malaysia DOSM)
    geojson_data = _load_kl_geojson()
    
    # Filter GeoJSON to only include Kuala Lumpur entries
    kl_features = [f for f in geojson_data["features"] if f["properties"].get("state") == "W.P. Kuala Lumpur"]
    kl_geojson = {"type": "FeatureCollection", "features": kl_features}

    st.subheader("🗺️ KL Mukim Price Heatmap")
    st.caption("Interactive choropleth map showing median price per sqft across KL mukims using official boundaries. Hover for details.")

    # Create choropleth map with reduced opacity and black legend
    map_fig = px.choropleth_mapbox(
        summary,
        geojson=kl_geojson,
        locations="name",
        featureidkey="properties.district",
        color="median_price_per_sqft",
        hover_name="name",
        hover_data={
            "name": False,
            "transactions": True,
            "median_price_per_sqft": ":.0f",
            "avg_price_per_sqft": ":.0f",
            "property_types": True,
        },
        labels={
            "median_price_per_sqft": "Median price / sqft (RM)",
            "transactions": "Transactions",
        },
        color_continuous_scale="YlOrRd",
        mapbox_style="carto-positron",
        zoom=9.8,
        center={"lat": 3.14, "lon": 101.69},
        height=520,
    )
    
    # Update traces for reduced opacity
    map_fig.update_traces(marker_opacity=0.6, marker_line_width=1.5, marker_line_color="#333")
    
    # Update layout: set legend to black background with readable text
    map_fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        paper_bgcolor="white",
        mapbox=dict(
            center={"lat": 3.14, "lon": 101.69},
            zoom=9.8,
        ),
        coloraxis_colorbar=dict(
            bgcolor="#1a1a1a",  # Black background for legend
            tickfont=dict(color="white"),
            # titlefont=dict(color="white"),
            thickness=15,
            len=0.7,
        ),
    )
    
    st.plotly_chart(map_fig, width='stretch')

    st.subheader("📊 Mukim Snapshot")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Selected property type", selected_group)
    with col2:
        st.metric("Mukims shown", f"{len(summary):,}")
    with col3:
        st.metric("Median price / sqft", f"RM {summary['median_price_per_sqft'].median():,.0f}" if not summary.empty else "RM 0")

    is_subscribed = role.lower() not in {"free", "guest", ""}
    if is_subscribed:
        st.dataframe(
            summary[["name", "transactions", "median_price_per_sqft", "avg_price_per_sqft", "property_types"]]
            .rename(columns={
                "name": "Mukim",
                "transactions": "Transactions",
                "median_price_per_sqft": "Median price/sqft (RM)",
                "avg_price_per_sqft": "Average price/sqft (RM)",
                "property_types": "Property types in view",
            })
            .sort_values("Transactions", ascending=False)
            .reset_index(drop=True),
            width='stretch',
            hide_index=True,
        )
