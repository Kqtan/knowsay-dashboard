import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from utils.auth import init_auth_state, render_auth_sidebar, render_reset_password_page, require_auth, get_current_user_role, get_current_user, ensure_valid_session
from utils.supabase_client import get_supabase_client
from utils.data_loader import load_property_data
from utils.mukim_map import render_mukim_map
from utils.data_gov_my import (
    get_kl_context,
    get_kl_affordability,
    get_poverty_for_map,
    render_parlimen_income_map,
    render_gdp_state_comparison,
    render_crime_overview,
    render_schools_overview,
    render_vehicle_registrations,
    render_state_demographics,
    render_kl_vital_stats,
)
from utils.mortgage import (
    calculate_mortgage_schedule,
    format_rm_input,
    parse_rm_input,
    render_metric_card,
    render_mortgage_calculator,
)


def get_role_label(role: str) -> str:
    """Return a friendly label for the current subscription tier."""
    return "Subscribed" if role.lower() in {"subscribed"} else "Free"


def _fake_price_distribution():
    """Generate a fake price distribution histogram for non-subscribed preview."""
    rng = np.random.default_rng(42)
    fake_prices = rng.lognormal(mean=13.5, sigma=0.8, size=500)
    fig = px.histogram(
        x=fake_prices,
        nbins=50,
        labels={'x': 'Transaction Price (RM)'},
        title="Price Distribution"
    )
    fig.update_layout(height=400, showlegend=False)
    fig.update_traces(marker_color='rgba(100,100,100,0.4)')
    return fig


def render_gated_chart(role: str, fig, feature_name: str, fake_fig_fn=None):
    """Render a Plotly chart with role-based access control.

    Subscribed users see the real chart.
    Free/guest users see a blurred fake preview with a subscribe overlay.
    """
    is_subscribed = role.lower() not in {"free", "guest", ""}

    if is_subscribed:
        st.plotly_chart(fig, width='stretch')
        return

    fake_fig = fake_fig_fn() if fake_fig_fn else fig
    chart_html = fake_fig.to_html(
        include_plotlyjs='cdn',
        full_html=False,
        config={'responsive': True, 'displayModeBar': False}
    )

    st.markdown(
        f"""
        <div style="position:relative; overflow:hidden; border-radius:8px; margin-bottom:1rem;">
            <div style="filter:blur(12px); pointer-events:none; user-select:none;
                        transform:scale(1.02);">
                {chart_html}
            </div>
            <div style="
                position:absolute; top:0; left:0; right:0; bottom:0;
                display:flex; flex-direction:column; justify-content:center; align-items:center;
                z-index:10;
            ">
                <div style="
                    background:rgba(255,255,255,0.93); border-radius:16px;
                    padding:1.5rem 2.5rem; text-align:center;
                    box-shadow:0 8px 32px rgba(0,0,0,0.12);
                    max-width:280px;
                ">
                    <div style="font-size:2.5rem; color:#252525">🔒</div>
                    <div style="font-size:1.1rem; font-weight:700; color:#1f2937; margin-top:0.25rem;">
                        Subscribe to view
                    </div>
                    <div style="font-size:0.85rem; color:#6b7280; margin-top:0.25rem;">
                        {feature_name} is available on the subscribed plan
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_subscription_banner(role: str) -> None:
    """Display a main-page subscription reminder or thank-you banner."""
    hidden = st.session_state.get("hide_subscription_banner", False)
    if hidden:
        return

    is_subscribed = role.lower() not in {"free", "guest", ""}
    col1, col2 = st.columns([0.95, 0.05])

    if is_subscribed:
        with col1:
            st.success(
            "Thank you for subscribing — KnowSay is fully unlocked. "
            "We appreciate your support and will keep improving the experience.",
                icon="🎉"
            )
    else:
        with col1:
            st.warning(
                "You are on the Free tier. Subscribe to unlock the full market view and advanced analytics.",
                icon="💡"
            )

    with col2:
        key = "close_subscription_banner" if is_subscribed else "dismiss_subscription_banner"
        if st.button("✕", key=key, help="Dismiss"):
            st.session_state.hide_subscription_banner = True
            st.rerun()

def parse_month_year(month_year_str):
    """Convert 'Month Year' string to datetime object."""
    try:
        return pd.to_datetime(month_year_str, format='%Y-%m')
    except:
        return None

def filter_data(df, property_types, districts, mukims, land_area_range, date_range, price_range=None):
    """Apply selected filters to data."""
    filtered_df = df.copy()
    
    if property_types:
        filtered_df = filtered_df[filtered_df['property_type_grouped'].isin(property_types)]
    
    if districts:
        filtered_df = filtered_df[filtered_df['district'].isin(districts)]
    
    if mukims:
        filtered_df = filtered_df[filtered_df['mukim'].isin(mukims)]
    
    if land_area_range:
        filtered_df = filtered_df[
            (filtered_df['land_area_sqft'] >= land_area_range[0]) &
            (filtered_df['land_area_sqft'] <= land_area_range[1])
        ]
    
    if price_range:
        filtered_df = filtered_df[
            (filtered_df['txn_price_rm'] >= price_range[0]) &
            (filtered_df['txn_price_rm'] <= price_range[1])
        ]
    
    if date_range:
        # Create a temporary datetime column for filtering
        filtered_df = filtered_df.copy()
        filtered_df['_txn_date'] = filtered_df['txn_mth_id'].apply(parse_month_year)
        filtered_df = filtered_df[
            (filtered_df['_txn_date'] >= date_range[0]) &
            (filtered_df['_txn_date'] <= date_range[1])
        ]
        filtered_df = filtered_df.drop('_txn_date', axis=1)
    
    return filtered_df



def main():
    st.set_page_config(page_title="KnowSay", layout="wide")

    init_auth_state()
    render_auth_sidebar()
    require_auth()

    # Show reset-password page instead of dashboard when in recovery flow
    if st.session_state.get("auth_page") == "reset_password":
        render_reset_password_page()
        return

    current_role = get_current_user_role()
    st.sidebar.info(f"KnowSay • {current_role.capitalize()}")

    st.title("🏘️ KnowSay")
    st.caption("Property & economic data for Malaysia — not hearsay, not guesses.")

    st.markdown("---")

    # Refresh token if close to expiry before loading data
    ensure_valid_session()

    # Load data
    df = load_property_data(
        st.session_state.get("auth_access_token"),
        current_role,
    )
    last_refreshed = pd.to_datetime(df['txn_mth_id'].dropna().max(), format='%Y-%m') + pd.offsets.MonthEnd(0)
    last_refreshed_label = last_refreshed.strftime('%d %b %Y')

    render_subscription_banner(current_role)

    hero_col, snapshot_col = st.columns([2, 1], gap="medium")
    with hero_col:
        st.markdown(
            """
            <div style="padding: 1rem 1rem; border-radius: 18px; background: linear-gradient(135deg, #0f172a, #1f2937); color: #f8fafc;">
              <div style="font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.18em; color: #bfdbfe;">Overview</div>
              <div style="font-size: 1.35rem; font-weight: 700; margin-top: 0.25rem;">Malaysia property & economic data — from the numbers, not from uncle</div>
              <div style="font-size: 0.98rem; color: #e5eefb; margin-top: 0.35rem;">Filter, compare, and analyse property trends, pricing, and market signals — backed by data, not hearsay.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with snapshot_col:
        st.info(f"Data refreshed as of {last_refreshed_label}", icon="🗓️")
        st.info(f"Active plan: {get_role_label(current_role)}", icon="💳")
    
    # Parse dates for min/max
    df_dates = df['txn_mth_id'].apply(parse_month_year).dropna()
    min_date = df_dates.min()
    max_date = df_dates.max()
    
    # Sidebar filters
    st.sidebar.title("📊 Filters")
    st.sidebar.markdown("---")
    
    # Date Range Filter
    st.sidebar.subheader("📅 Date Range")
    date_range = st.sidebar.date_input(
        "Select Transaction Date Range",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date()
    )
    
    # Convert to datetime for filtering
    if len(date_range) == 2:
        date_filter = (
            pd.Timestamp(date_range[0]),
            pd.Timestamp(date_range[1])
        )
    else:
        date_filter = None
    
    st.sidebar.markdown("---")
    # Property Type Filter
    all_property_types = sorted(df['property_type_grouped'].dropna().unique().tolist())
    selected_property_types = st.sidebar.multiselect(
        "Property Type",
        options=all_property_types,
        default=['Terrace', 'Condominium/Apartment']
        # all_property_types[:3] if len(all_property_types) > 0 else []
    )
    
    # District Filter
    all_districts = sorted(df['district'].dropna().unique().tolist())
    selected_districts = st.sidebar.multiselect(
        "District",
        options=all_districts,
        default=all_districts[:3] if len(all_districts) > 0 else []
    )
    
    # Mukim Filter (conditional on district selection)
    if selected_districts:
        available_mukims = sorted(
            df[df['district'].isin(selected_districts)]['mukim'].dropna().unique().tolist()
        )
    else:
        available_mukims = sorted(df['mukim'].dropna().unique().tolist())
    
    selected_mukims = st.sidebar.multiselect(
        "Mukim",
        options=available_mukims,
        default=available_mukims[:3] if len(available_mukims) > 0 else []
    )
    
    # Land Area and Price Range — subscribed only
    is_subscribed = current_role.lower() not in {"free", "guest", ""}

    if is_subscribed:
        st.sidebar.subheader("📐 Land Area (sqft)")
        min_area = int(df['land_area_sqft'].min())
        max_area = int(df['land_area_sqft'].max())

        land_area_min = st.sidebar.number_input(
            "Minimum Land Area (sqft)",
            min_value=min_area,
            max_value=max_area,
            value=min_area,
            step=10,
            format="%d",
            help="Enter the exact minimum land area in square feet."
        )
        land_area_max = st.sidebar.number_input(
            "Maximum Land Area (sqft)",
            min_value=min_area,
            max_value=max_area,
            value=max_area,
            step=10,
            format="%d",
            help="Enter the exact maximum land area in square feet."
        )

        if land_area_min > land_area_max:
            st.sidebar.error("Minimum sqft cannot exceed maximum sqft.")
            land_area_max = land_area_min

        land_area_range = st.sidebar.slider(
            "Land Area (sqft)",
            min_value=min_area,
            max_value=max_area,
            value=(land_area_min, land_area_max),
            step=50,
            format="%,d"
        )

        st.sidebar.subheader("💰 Price (RM)")
        min_price = int(df['txn_price_rm'].min())
        max_price = int(df['txn_price_rm'].max())
        price_range = st.sidebar.slider(
            "Price Range (RM)",
            min_value=min_price,
            max_value=max_price,
            value=(min_price, max_price),
            step=50000,
            format="RM %,d"
        )
    else:
        st.sidebar.markdown(
            '<div style="background:#1f2937; border-radius:10px; padding:0.8rem 1rem; '
            'text-align:center; font-size:0.85rem; color:#9ca3af;">'
            '🔒 <strong>Land Area & Price filters</strong><br>'
            'upgrade to subscribed tier</div>',
            unsafe_allow_html=True,
        )
        land_area_range = None
        price_range = None

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Reset Filters",  width='stretch'):
        st.rerun()
    
    st.sidebar.markdown("---")
    total_count = len(df)
    
    # Apply filters
    filtered_df = filter_data(df, selected_property_types, selected_districts, selected_mukims, land_area_range, date_filter, price_range)
    
    active_count = len(filtered_df)
    st.sidebar.markdown(f"**Filter Summary**")
    st.sidebar.markdown(f"Showing **{active_count:,}** of **{total_count:,}** transactions")
    if active_count < total_count:
        st.sidebar.markdown(f"*({total_count - active_count:,} rows filtered out)*")
    
    # Display key metrics
    st.subheader("📈 Key Metrics")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Transactions", f"{len(filtered_df):,}")
    
    with col2:
        avg_price_per_sqft = (filtered_df['txn_price_per_sqft']).mean() if len(filtered_df) > 0 else 0
        st.metric("Average Price per sqft", f"RM {avg_price_per_sqft:,.0f}")
    
    with col3:
        median_price_per_sqft = (filtered_df['txn_price_per_sqft']).median() if len(filtered_df) > 0 else 0
        st.metric("Median Price per sqft", f"RM {median_price_per_sqft:,.0f}")
    
    with col4:
        avg_land_area = filtered_df['land_area_sqft'].mean() if len(filtered_df) > 0 else 0
        st.metric("Avg Land Area", f"{avg_land_area:,.0f} sqft")
    
    st.markdown("---")

    # Create tabbed interface for different visualizations
    tab_charts, tab_map, tab_socio, tab_mortgage = st.tabs([
        "📊 Charts",
        "🗺️ Mukim Map",
        "🌐 Socioeconomic Insights",
        "🧮 Mortgage Calculator",
    ])
    
    
    with tab_charts:
        # Charts - Two columns layout
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("Transactions by Property Type")
            if len(filtered_df) > 0:
                prop_type_counts = filtered_df['property_type_grouped'].value_counts().head(10)
                fig_prop_type = px.bar(
                    x=prop_type_counts.values,
                    y=prop_type_counts.index,
                    orientation='h',
                    labels={'x': 'Count', 'y': 'Property Type'},
                    title="Top 10 Property Types"
                )
                fig_prop_type.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_prop_type,  width='stretch')
            else:
                st.info("No data available for selected filters")
        
        with col_right:
            st.subheader("Transactions by Mukim")
            if len(filtered_df) > 0:
                district_counts = filtered_df['mukim'].value_counts().head(10)
                fig_district = px.bar(
                    x=district_counts.values,
                    y=district_counts.index,
                    orientation='h',
                    labels={'x': 'Count', 'y': 'Mukim'},
                    title="Top 10 Districts"
                )
                fig_district.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_district,  width='stretch')
            else:
                st.info("No data available for selected filters")
        
        # Transactions over time
        st.subheader("📊 Transactions Over Time")
        if len(filtered_df) > 0:
            # Parse dates and group by month
            filtered_df_copy = filtered_df.copy()
            filtered_df_copy['_txn_date'] = filtered_df_copy['txn_mth_id'].apply(parse_month_year)
            time_series = filtered_df_copy.groupby('_txn_date').size().reset_index(name='count')
            
            fig_time = px.line(
                time_series,
                x='_txn_date',
                y='count',
                labels={'_txn_date': 'Month', 'count': 'Number of Transactions'},
                title="Transaction Count Over Time",
                markers=True
            )
            fig_time.update_layout(height=400, hovermode='x unified')
            st.plotly_chart(fig_time, width='stretch')
        else:
            st.info("No data available for selected filters")
        
        # Market Pricing Insights
        st.subheader("💰 Market Pricing Insights")
        col_left, col_right = st.columns(2)

        with col_left:
            if len(filtered_df) > 0:
                district_psf = (
                    filtered_df.groupby("mukim")["txn_price_per_sqft"]
                    .agg(median="median", count="count")
                    .reset_index()
                    .sort_values("median", ascending=True)
                )
                fig_dist_psf = px.bar(
                    district_psf,
                    y="mukim",
                    x="median",
                    orientation="h",
                    labels={"mukim": "", "median": "Median Price per sqft (RM)"},
                    title="Median Price per sqft by Mukim",
                    text_auto=",.0f",
                )
                fig_dist_psf.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_dist_psf, width="stretch")
            else:
                st.info("No data available for selected filters")

        with col_right:
            if len(filtered_df) > 0:
                df_trend = filtered_df.copy()
                df_trend["_txn_date"] = df_trend["txn_mth_id"].apply(parse_month_year)
                monthly_median = (
                    df_trend.groupby("_txn_date")["txn_price_rm"]
                    .median()
                    .reset_index()
                )
                fig_price_trend = px.line(
                    monthly_median,
                    x="_txn_date",
                    y="txn_price_rm",
                    labels={"_txn_date": "Month", "txn_price_rm": "Median Price (RM)"},
                    title="Median Transaction Price Over Time",
                    markers=True,
                )
                fig_price_trend.update_layout(height=400, hovermode="x unified")
                st.plotly_chart(fig_price_trend, width="stretch")
            else:
                st.info("No data available for selected filters")

        st.subheader("📈 Price & Size Relationships")
        col_left, col_right = st.columns(2)

        with col_left:
            if len(filtered_df) > 0:
                top_types = filtered_df['property_type_grouped'].value_counts().head(10).index.tolist()
                df_box = filtered_df[filtered_df['property_type_grouped'].isin(top_types)]
                fig_box = px.box(
                    df_box,
                    x='property_type_grouped',
                    y='txn_price_rm',
                    labels={'property_type_grouped': 'Property Type', 'txn_price_rm': 'Price (RM)'},
                    title="Price Distribution by Property Type"
                )
                fig_box.update_layout(height=400)
                st.plotly_chart(fig_box, width="stretch")
            else:
                st.info("No data available for selected filters")

        with col_right:
            if len(filtered_df) > 0:
                sample = filtered_df.sample(n=min(1000, len(filtered_df)))
                fig_scatter = px.scatter(
                    sample,
                    x='land_area_sqft',
                    y='txn_price_rm',
                    color='property_type_grouped',
                    labels={'land_area_sqft': 'Land Area (sqft)', 'txn_price_rm': 'Price (RM)'},
                    title="Price vs Land Area",
                    opacity=0.5
                )
                fig_scatter.update_layout(height=400)
                render_gated_chart(current_role, fig_scatter, "Price vs Land Area",
                                fake_fig_fn=_fake_price_distribution)
                # st.plotly_chart(fig_scatter, width="stretch")
            else:
                st.info("No data available for selected filters")

        st.subheader("Price Distribution")
        col_left, col_right = st.columns(2)
        
        with col_left:
            if len(filtered_df) > 0:
                fig_price_dist = px.histogram(
                    filtered_df,
                    x='txn_price_rm',
                    nbins=50,
                    labels={'txn_price_rm': 'Transaction Price (RM)'},
                    title="Price Distribution"
                )
                fig_price_dist.update_layout(height=400, showlegend=False)
                render_gated_chart(current_role, fig_price_dist, "Price Distribution",
                                fake_fig_fn=_fake_price_distribution)
            else:
                st.info("No data available for selected filters")
        
        with col_right:
            if len(filtered_df) > 0:
                fig_floor_area = px.histogram(
                    filtered_df,
                    x='land_area_sqft',
                    nbins=50,
                    labels={'land_area_sqft': 'Property Size (sqft)'},
                    title="Area sqft Distribution"
                )
                fig_floor_area.update_layout(height=400, showlegend=False)
                render_gated_chart(current_role, fig_floor_area, "Area sqft Distribution",
                                fake_fig_fn=_fake_price_distribution)
            else:
                st.info("No data available for selected filters")
        
        # Tenure breakdown
        st.subheader("🕔 Tenure Analysis")
        col_left, col_right = st.columns(2)
        
        with col_left:
            if len(filtered_df) > 0:
                tenure_counts = filtered_df['tenure'].value_counts()
                fig_tenure = px.pie(
                    values=tenure_counts.values,
                    names=tenure_counts.index,
                    title="Property Tenure Breakdown"
                )
                fig_tenure.update_layout(height=400)
                st.plotly_chart(fig_tenure, width='stretch')
            else:
                st.info("No data available for selected filters")
        
        with col_right:
            if len(filtered_df) > 0 and filtered_df['unit_level'].notna().any():
                unit_level_counts = filtered_df['unit_level'].value_counts().head(10)
                fig_unit_level = px.bar(
                    x=unit_level_counts.index,
                    y=unit_level_counts.values,
                    labels={'x': 'Unit Level', 'y': 'Count'},
                    title="Top 10 Unit Levels"
                )
                fig_unit_level.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_unit_level, width='stretch')
            else:
                st.info("No data available for selected filters")
    
    with tab_map:
        render_mukim_map(filtered_df, role=current_role)

    with tab_socio:
        kl_ctx = get_kl_context()
        kl_afford = get_kl_affordability(filtered_df)

        if kl_ctx:
            st.subheader("🌐 KL Market Context")
            cc = st.columns(5)
            labels = [
                ("Population", f"{kl_ctx.get('population', 0):,}", "👥"),
                ("Median Income", f"RM {kl_ctx.get('income_median', 0):,}" if kl_ctx.get('income_median') else "N/A", "💰"),
                ("Gini Coefficient", f"{kl_ctx.get('hies_gini', 0):.3f}" if kl_ctx.get('hies_gini') else "N/A", "📊"),
                ("Poverty Rate", f"{kl_ctx.get('hies_poverty', 0):.1f}%" if kl_ctx.get('hies_poverty') else "N/A", "📉"),
                ("Mean Expenditure", f"RM {kl_ctx.get('hies_expenditure_mean', 0):,}" if kl_ctx.get('hies_expenditure_mean') else "N/A", "🛒"),
            ]
            for col, (label, value, icon) in zip(cc, labels):
                col.metric(f"{icon} {label}", value)
            if kl_ctx.get("gdp_value"):
                st.caption(f"GDP (constant 2015 prices): RM {kl_ctx['gdp_value']:,.2f} million | Data sourced from data.gov.my")

        else:
            st.caption("Market context data could not be loaded.")

        if kl_afford:
            st.subheader("🏠 Affordability Insights")

            monthly_income = kl_afford["median_income"]
            annual_income = monthly_income * 12
            annual_ratio = kl_afford["median_price"] / annual_income
            affordable_at_3x = annual_income * 3

            txn_per_capita = len(filtered_df) / kl_afford["ctx"]["population"] * 1000 if kl_afford["ctx"].get("population") else None

            ac1, ac2, ac3, ac4, ac5 = st.columns(5)
            ac1.metric("Median Price (KL)", f"RM {kl_afford['median_price']:,.0f}")
            ac2.metric("Median Annual Income", f"RM {annual_income:,.0f}")
            ac3.metric("Price / Annual Income", f"{annual_ratio:.1f}x")
            ac4.metric("Affordable at 3x Rule", f"RM {affordable_at_3x:,.0f}")
            if txn_per_capita:
                ac5.metric("Transactions / 1K pop.", f"{txn_per_capita:.1f}")

            ratio_label = f"{annual_ratio:.1f}x"
            if annual_ratio <= 3:
                st.success(
                    f"The median KL home costs **{ratio_label}** of annual household income "
                    f"— within the **3x rule of thumb** for affordable housing.",
                    icon="✅"
                )
            elif annual_ratio <= 5:
                st.warning(
                    f"The median KL home costs **{ratio_label}** of annual household income "
                    f"— above the **3x rule of thumb**. Housing is moderately unaffordable "
                    f"for the median household.",
                    icon="⚠️"
                )
            else:
                st.error(
                    f"The median KL home costs **{ratio_label}** of annual household income "
                    f"— far above the **3x rule of thumb**. Housing is severely unaffordable "
                    f"for the median household.",
                    icon="❌"
                )

            shortfall = kl_afford['median_price'] - affordable_at_3x
            if shortfall > 0:
                st.info(
                    f"The median household can afford up to **RM {affordable_at_3x:,.0f}** under the 3x rule, "
                    f"but the median home costs **RM {kl_afford['median_price']:,.0f}** — "
                    f"a gap of **RM {shortfall:,.0f}**.",
                    icon="📏"
                )
            else:
                st.info(
                    f"The median home is within the 3x annual income threshold.",
                    icon="📏"
                )

            if len(filtered_df) > 0 and is_subscribed:
                df_afford = filtered_df.copy()
                df_afford["_txn_date"] = df_afford["txn_mth_id"].apply(parse_month_year)
                monthly_med_price = df_afford.groupby("_txn_date")["txn_price_rm"].median().reset_index()
                fig_afford = px.line(
                    monthly_med_price,
                    x="_txn_date",
                    y="txn_price_rm",
                    labels={"_txn_date": "Month", "txn_price_rm": "Median Price (RM)"},
                    title="Median Price Trend vs 3x Annual Income Threshold",
                    markers=True,
                )
                fig_afford.add_hline(
                    y=affordable_at_3x,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Affordable max (3x annual income) RM {affordable_at_3x:,.0f}",
                )
                fig_afford.update_layout(height=400, hovermode="x unified")
                render_gated_chart(current_role, fig_afford, "Affordability Trends")
            elif len(filtered_df) > 0:
                fig_afford_placeholder = px.line(title="Affordability Trends")
                fig_afford_placeholder.update_layout(height=400)
                render_gated_chart(
                    current_role, fig_afford_placeholder,
                    "Affordability Trends",
                    fake_fig_fn=_fake_price_distribution,
                )
        else:
            st.caption("Affordability data could not be computed. Ensure KL property data and income data are available.")

        st.markdown("---")
        render_state_demographics()
        st.markdown("---")
        render_gdp_state_comparison()
        st.markdown("---")
        render_kl_vital_stats(filtered_df, role=current_role)
        st.markdown("---")
        render_parlimen_income_map()
        st.markdown("---")
        render_crime_overview(population=kl_ctx.get("population") if kl_ctx else None)
        st.markdown("---")
        render_schools_overview(population=kl_ctx.get("population") if kl_ctx else None)
        st.markdown("---")
        render_vehicle_registrations()
        st.markdown("---")

        kl_pov = get_poverty_for_map()
        if kl_pov:
            st.subheader("📉 Socioeconomic Context")
            pc1, pc2 = st.columns(2)
            pc1.metric("Absolute Poverty Rate (KL)", f"{kl_pov['poverty_absolute']:.1f}%")
            pc2.metric("Relative Poverty Rate (KL)", f"{kl_pov['poverty_relative']:.1f}%")
            st.caption("Poverty rates at district level (W.P. Kuala Lumpur) sourced from DOSM via data.gov.my.")

    with tab_mortgage:
        median_kl_price = df["txn_price_rm"].median() if len(df) > 0 else None
        render_mortgage_calculator(median_kl_price=median_kl_price)

    st.markdown("---")
    st.caption("© 2026 KnowSay. All rights reserved. Powered by data, not hearsay.")


if __name__ == "__main__":
    main()
