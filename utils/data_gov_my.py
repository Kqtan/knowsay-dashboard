import json
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
import requests

BASE_URL = "https://api.data.gov.my"
PARLIMEN_GEOJSON_URL = "https://raw.githubusercontent.com/dosm-malaysia/data-open/main/datasets/geodata/electoral_0_parlimen.geojson"


def _fetch_json(url: str, timeout: int = 30) -> list[dict]:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fetch_json_params(url: str, params: dict, timeout: int = 30) -> list[dict]:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner=False, ttl=3600)
def load_income_district() -> pd.DataFrame:
    data = _fetch_json(
        f"{BASE_URL}/data-catalogue?id=hh_income_district"
        "&include=state,district,income_mean,income_median,date"
        "&limit=10000"
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=3600)
def load_population_district() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "population_state",
            "include": "state,population,date,age,sex,ethnicity",
            "limit": 5000,
        },
    )
    df = pd.DataFrame(data)
    df = df[
        (df["sex"] == "overall_sex")
        & (df["age"] == "overall_age")
        & (df["ethnicity"] == "overall_ethnicity")
    ].copy()
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_poverty_district() -> pd.DataFrame:
    data = _fetch_json(
        f"{BASE_URL}/data-catalogue?id=hh_poverty_district"
        "&include=state,district,poverty_absolute,poverty_relative,date"
        "&limit=10000"
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=3600)
def load_hies_state() -> pd.DataFrame:
    data = _fetch_json(
        f"{BASE_URL}/opendosm?id=hies_state&limit=100"
    )
    df = pd.DataFrame(data)
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_gdp_district() -> pd.DataFrame:
    data = _fetch_json(
        f"{BASE_URL}/data-catalogue?id=gdp_district_real_supply"
        "&include=state,district,date,value,sector,series"
        "&limit=10000"
    )
    df = pd.DataFrame(data)
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_gdp_state() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "gdp_state_real_supply",
            "include": "state,date,value,sector,series",
            "filter": "p0@sector",
            "limit": 500,
        },
    )
    df = pd.DataFrame(data)
    if not df.empty and "series" in df.columns:
        df = df[df["series"] == "abs"]
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_crime_district() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "crime_district",
            "ifilter": "W.P. Kuala Lumpur@state",
            "limit": 5000,
        },
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=3600)
def load_schools_district() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "schools_district",
            "include": "state,district,stage,type,schools,date",
            "limit": 5000,
        },
    )
    df = pd.DataFrame(data)
    return df[df["state"] == "W.P. Kuala Lumpur"].copy()


@st.cache_data(show_spinner=False, ttl=3600)
def load_vehicle_registrations() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "registrations_type_fuel",
            "include": "date,fuel,type,registrations",
            "limit": 5000,
        },
    )
    df = pd.DataFrame(data)
    df = df[(df["fuel"] == "all_fuels") & (df["type"] == "all_types")].copy()
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def load_income_parlimen() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "hh_income_parlimen",
            "include": "state,parlimen,income_mean,income_median,date",
            "limit": 10000,
        },
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=86400)
def load_parlimen_geojson() -> dict:
    resp = requests.get(PARLIMEN_GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def render_parlimen_income_map():
    try:
        income_df = load_income_parlimen()
        geojson = load_parlimen_geojson()
    except Exception:
        st.caption("Parlimen income map could not be loaded.")
        return

    kl_income = income_df[income_df["state"] == "W.P. Kuala Lumpur"].copy()
    if kl_income.empty:
        st.caption("No income data available for KL parlimen constituencies.")
        return

    latest_year = kl_income["date"].max()
    kl_income = kl_income[kl_income["date"] == latest_year]

    kl_features = [f for f in geojson["features"] if f["properties"].get("state") == "W.P. Kuala Lumpur"]
    kl_geojson = {"type": "FeatureCollection", "features": kl_features}

    st.subheader(f"🗺️ Median Household Income by Parliament Constituency ({latest_year[:4]})")
    st.caption("Choropleth map of median household income across KL's 11 parliamentary constituencies. Hover for details.")

    fig = px.choropleth_mapbox(
        kl_income,
        geojson=kl_geojson,
        locations="parlimen",
        featureidkey="properties.parlimen",
        color="income_median",
        hover_name="parlimen",
        hover_data={
            "parlimen": False,
            "income_median": ":,",
            "income_mean": ":,",
        },
        labels={
            "income_median": "Median Income (RM)",
            "income_mean": "Mean Income (RM)",
        },
        color_continuous_scale="Greens",
        mapbox_style="carto-positron",
        zoom=9.8,
        center={"lat": 3.14, "lon": 101.69},
        height=520,
    )

    fig.update_traces(marker_opacity=0.7, marker_line_width=1.5, marker_line_color="#333")
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        paper_bgcolor="white",
        mapbox=dict(
            center={"lat": 3.14, "lon": 101.69},
            zoom=9.8,
        ),
    )
    st.plotly_chart(fig, width="stretch")


def render_gdp_state_comparison():
    try:
        df = load_gdp_state()
    except Exception:
        st.caption("GDP comparison could not be loaded.")
        return

    key_states = ["W.P. Kuala Lumpur", "Selangor", "Johor", "Pulau Pinang", "Sarawak", "Sabah"]
    plot_df = df[df["state"].isin(key_states)].copy()
    if plot_df.empty:
        st.caption("No GDP data available.")
        return

    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df = plot_df.sort_values("date")

    st.subheader("📊 Real GDP Comparison by State (Constant 2015 Prices)")
    st.caption("Annual real GDP (RM million) for key Malaysian states. Hover for details.")

    fig = px.line(
        plot_df,
        x="date",
        y="value",
        color="state",
        markers=True,
        labels={"date": "Year", "value": "GDP (RM million)", "state": ""},
        title="Real GDP: KL vs Other States",
    )
    fig.update_layout(height=400, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def render_crime_overview(population: int | None = None):
    try:
        df = load_crime_district()
    except Exception:
        st.caption("Crime data could not be loaded.")
        return

    if df.empty:
        st.caption("No crime data available for KL.")
        return

    st.subheader("🚔 Crime Overview — Kuala Lumpur")
    st.caption("Annual crime incidents by category in KL. Data sourced from PDRM via data.gov.my.")

    total = df[df["type"] == "all"].sort_values("date")
    if not total.empty:
        latest = total["date"].max()
        latest_total = total[total["date"] == latest]["crimes"].sum()
        total_2016 = total[total["date"] == "2016-01-01"]["crimes"].sum() if "2016-01-01" in total["date"].values else None

        c1, c2 = st.columns(2)
        c1.metric(
            f"Total Crimes ({latest[:4]})",
            f"{int(latest_total):,}",
            delta=f"{((latest_total - total_2016) / total_2016 * 100):+.1f}% vs 2016" if total_2016 else None,
        )
        if population:
            rate = latest_total / population * 1000
            c2.metric("Crime Rate", f"{rate:.2f}", help="per 1,000 population")

    st.markdown("#### Crime Trends Over Time")
    summary = df[df["type"] == "all"].pivot_table(
        index="date", columns="category", values="crimes", aggfunc="sum"
    ).reset_index()
    summary["date"] = pd.to_datetime(summary["date"])

    fig = px.area(
        summary,
        x="date",
        y=["assault", "property"],
        labels={"date": "Year", "value": "Number of Crimes", "variable": "Category"},
        title="Crime Trends in KL by Category",
    )
    fig.update_layout(height=350, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Crimes by Police District")
    district_data = df[(df["type"] == "all") & (df["district"] != "All")]
    latest_district = district_data[district_data["date"] == latest].copy()
    if not latest_district.empty:
        latest_district["total"] = latest_district.groupby("district")["crimes"].transform("sum")
        fig2 = px.bar(
            latest_district,
            x="district",
            y="crimes",
            color="category",
            barmode="group",
            labels={"district": "Police District", "crimes": "Number of Crimes", "category": "Category"},
            title=f"Crime Incidents by Police District ({latest[:4]})",
            text_auto=".0f",
        )
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, width="stretch")


@st.cache_data(show_spinner=False, ttl=3600)
def load_population_age_kl() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "population_district",
            "include": "state,district,age,sex,ethnicity,population,date",
            "ifilter": "W.P. Kuala Lumpur@state",
            "limit": 1000,
        },
    )
    df = pd.DataFrame(data)
    df = df[(df["sex"] == "both") & (df["ethnicity"] == "overall")].copy()
    return df


def render_schools_overview(population: int | None = None):
    try:
        df = load_schools_district()
        age_df = load_population_age_kl()
    except Exception:
        st.caption("Schools data could not be loaded.")
        return

    if df.empty:
        st.caption("No schools data available for KL.")
        return

    st.subheader("🏫 Schools in Kuala Lumpur")
    st.caption("Number of public education institutions by stage over time. Data sourced from MOE via data.gov.my.")

    plot_df = df[df["district"] == "All Districts"].copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df = plot_df.sort_values("date")
    latest = plot_df["date"].max()

    stage_totals = plot_df.groupby(["date", "stage"], as_index=False)["schools"].sum()
    latest_totals = stage_totals[stage_totals["date"] == latest]

    if not latest_totals.empty:
        primary_schools = int(latest_totals[latest_totals["stage"] == "primary"]["schools"].sum())
        secondary_schools = int(latest_totals[latest_totals["stage"] == "secondary"]["schools"].sum())
        total_schools = int(latest_totals["schools"].sum())

        st.subheader("📊 School vs Population Ratios")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Primary Schools", f"{primary_schools:,}")
        col2.metric("Secondary Schools", f"{secondary_schools:,}")
        col3.metric("Total Schools", f"{total_schools:,}")
        if population:
            col4.metric("Population per School", f"{population / total_schools:,.0f}")

        if not age_df.empty:
            latest_age = age_df["date"].max()

            primary_age_pop = age_df[age_df["age"].isin(["5-9", "10-14"])]
            primary_age_pop = primary_age_pop[primary_age_pop["date"] == latest_age]["population"].sum() * 1000

            secondary_age_pop = age_df[age_df["age"] == "15-19"]
            secondary_age_pop = secondary_age_pop[secondary_age_pop["date"] == latest_age]["population"].sum() * 1000

            c1, c2 = st.columns(2)
            c1.metric(
                f"Children per Primary School (age 5-14)",
                f"{int(primary_age_pop / primary_schools):,}",
                help=f"Population aged 5-14 ({int(primary_age_pop):,}) divided by primary schools ({primary_schools})",
            )
            c2.metric(
                f"Young People per Secondary School (age 15-19)",
                f"{int(secondary_age_pop / secondary_schools):,}",
                help=f"Population aged 15-19 ({int(secondary_age_pop):,}) divided by secondary schools ({secondary_schools})",
            )

    fig = px.bar(
        stage_totals,
        x="date",
        y="schools",
        color="stage",
        barmode="group",
        labels={"date": "Year", "schools": "Number of Schools", "stage": "Stage"},
        title=f"Public Schools in KL by Stage ({stage_totals['date'].min().year}–{latest.year})",
        text_auto=".0f",
    )
    fig.update_layout(height=400, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def render_vehicle_registrations():
    try:
        df = load_vehicle_registrations()
    except Exception:
        st.caption("Vehicle registration data could not be loaded.")
        return

    if df.empty:
        st.caption("No vehicle registration data available.")
        return

    st.subheader("🚗 National Vehicle Registration Trends")
    st.caption("Monthly vehicle registrations (all fuel types) across Malaysia. Data sourced from JPJ via data.gov.my.")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    latest = df["date"].max()
    latest_reg = df[df["date"] == latest]["registrations"].sum()
    st.metric(f"Latest Monthly Registrations ({latest.strftime('%b %Y')})", f"{int(latest_reg):,}")

    fig = px.line(
        df,
        x="date",
        y="registrations",
        labels={"date": "Year", "registrations": "Registrations"},
        title="Monthly Vehicle Registrations (All Types)",
    )
    fig.update_layout(height=350, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def get_kl_context():
    try:
        income_df = load_income_district()
        population_df = load_population_district()
        poverty_df = load_poverty_district()
        hies_df = load_hies_state()
        gdp_df = load_gdp_district()
    except Exception:
        return None

    kl_income = income_df[income_df["state"] == "W.P. Kuala Lumpur"]
    kl_pop = population_df[population_df["state"] == "W.P. Kuala Lumpur"]
    kl_poverty = poverty_df[poverty_df["state"] == "W.P. Kuala Lumpur"]
    kl_hies = hies_df[hies_df["state"] == "W.P. Kuala Lumpur"]
    kl_gdp = gdp_df[gdp_df["state"] == "W.P. Kuala Lumpur"]

    ctx = {}

    if not kl_pop.empty:
        latest_pop = kl_pop[kl_pop["date"] == kl_pop["date"].max()]
        if not latest_pop.empty:
            ctx["population"] = int(latest_pop["population"].iloc[0] * 1000)

    if not kl_income.empty:
        latest = kl_income[kl_income["date"] == kl_income["date"].max()]
        if not latest.empty:
            ctx["income_median"] = int(latest["income_median"].iloc[0])
            ctx["income_mean"] = int(latest["income_mean"].iloc[0])

    if not kl_poverty.empty:
        latest = kl_poverty[kl_poverty["date"] == kl_poverty["date"].max()]
        if not latest.empty:
            ctx["poverty_absolute"] = latest["poverty_absolute"].iloc[0]
            ctx["poverty_relative"] = latest["poverty_relative"].iloc[0]

    if not kl_hies.empty:
        latest = kl_hies[kl_hies["date"] == kl_hies["date"].max()]
        if not latest.empty:
            row = latest.iloc[0]
            ctx["hies_income_mean"] = int(row.get("income_mean", 0))
            ctx["hies_income_median"] = int(row.get("income_median", 0))
            ctx["hies_expenditure_mean"] = int(row.get("expenditure_mean", 0))
            ctx["hies_gini"] = float(row.get("gini", 0))
            ctx["hies_poverty"] = float(row.get("poverty", 0))

    if not kl_gdp.empty:
        total_gdp = kl_gdp[kl_gdp["sector"] == "p0"]
        if not total_gdp.empty:
            latest = total_gdp[total_gdp["date"] == total_gdp["date"].max()]
            if not latest.empty:
                ctx["gdp_value"] = float(latest["value"].iloc[0])

    return ctx if ctx else None


def get_kl_affordability(property_df: pd.DataFrame) -> dict | None:
    ctx = get_kl_context()
    if ctx is None:
        return None

    kl_props = property_df[property_df["district"] == "Kuala Lumpur"]
    if kl_props.empty:
        return None

    median_price = kl_props["txn_price_rm"].median()
    median_income = ctx.get("income_median") or ctx.get("hies_income_median")
    mean_income = ctx.get("income_mean") or ctx.get("hies_income_mean")

    if not median_income:
        return None

    return {
        "median_price": median_price,
        "median_income": median_income,
        "mean_income": mean_income,
        "price_to_income_ratio": median_price / median_income,
        "ctx": ctx,
    }


@st.cache_data(show_spinner=False, ttl=3600)
def load_population_state() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "population_state",
            "include": "state,age,sex,ethnicity,population,date",
            "limit": 5000,
        },
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=3600)
def load_births_kl() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "births_district_sex",
            "include": "state,district,sex,abs,date",
            "ifilter": "W.P. Kuala Lumpur@state",
            "limit": 100,
        },
    )
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False, ttl=3600)
def load_deaths_kl() -> pd.DataFrame:
    data = _fetch_json_params(
        f"{BASE_URL}/data-catalogue",
        {
            "id": "deaths_district_sex",
            "include": "state,district,sex,abs,date",
            "ifilter": "W.P. Kuala Lumpur@state",
            "limit": 100,
        },
    )
    return pd.DataFrame(data)


def render_state_demographics():
    try:
        pop_df = load_population_state()
    except Exception:
        st.caption("State demographic data could not be loaded.")
        return

    if pop_df.empty:
        return

    st.subheader("📊 KL vs Other States — Demographics")
    st.caption("Comparing KL with Selangor, Johor, and Penang (Pulau Pinang) across key demographic indicators. Data: DOSM via data.gov.my.")

    comparison_states = ["W.P. Kuala Lumpur", "Selangor", "Johor", "Pulau Pinang"]
    state_data = pop_df[pop_df["state"].isin(comparison_states)]

    # --- Population Density ---
    st.markdown("#### Population Density")
    area_km2 = {"W.P. Kuala Lumpur": 243, "Selangor": 8104, "Johor": 19210, "Pulau Pinang": 1048}
    overall = state_data[(state_data["age"] == "overall_age") & (state_data["sex"] == "overall_sex") & (state_data["ethnicity"] == "overall_ethnicity")]
    latest = overall["date"].max()
    latest_pop = overall[overall["date"] == latest]

    cols = st.columns(len(comparison_states))
    for col, state in zip(cols, comparison_states):
        rec = latest_pop[latest_pop["state"] == state]
        if not rec.empty:
            pop_val = rec["population"].iloc[0] * 1000
            area = area_km2.get(state, 1)
            density = pop_val / area
            col.metric(f"{state}", f"{int(density):,}/km²", help=f"Population: {int(pop_val):,} | Area: {area:,} km²")

    # --- Age Groups ---
    st.markdown("#### Age Group Distribution")
    age_data = state_data[(state_data["sex"] == "overall_sex") & (state_data["ethnicity"] == "overall_ethnicity") & (state_data["date"] == latest)]
    age_data = age_data[~age_data["age"].isin(["overall_age", "overall_ethnicity"])]
    age_data["age_group"] = age_data["age"].apply(
        lambda a: "0-14 (Children)" if a in ("0-4", "5-9", "10-14")
        else "65+ (Elderly)" if a in ("65-69", "70-74", "75-79", "80-84", "85+")
        else "15-64 (Working Age)"
    )
    age_grouped = age_data.groupby(["state", "age_group"], as_index=False)["population"].sum()
    age_grouped["population"] = age_grouped["population"] * 1000
    age_grouped["state"] = pd.Categorical(age_grouped["state"], categories=comparison_states, ordered=True)
    age_grouped = age_grouped.sort_values("state")

    fig_age = px.bar(
        age_grouped,
        x="state",
        y="population",
        color="age_group",
        barmode="group",
        labels={"state": "State", "population": "Population", "age_group": "Age Group"},
        title=f"Age Group Distribution ({latest[:4]})",
    )
    fig_age.update_layout(height=400, legend_title="Age Group")
    st.plotly_chart(fig_age, width="stretch")

    # --- Ethnicity ---
    ethnicities_avail = state_data["ethnicity"].unique()
    if "overall_ethnicity" in ethnicities_avail and "bumi_malay" in ethnicities_avail:
        st.markdown("#### Ethnic Composition")
        ethnic_data = state_data[(state_data["age"] == "overall_age") & (state_data["sex"] == "overall_sex") & (state_data["date"] == latest)]
        ethnic_data = ethnic_data[ethnic_data["ethnicity"].isin(["bumi_malay", "overall_ethnicity"])].copy()
        if not ethnic_data.empty:
            overall_pops = ethnic_data[ethnic_data["ethnicity"] == "overall_ethnicity"].set_index("state")["population"]
            malay_pops = ethnic_data[ethnic_data["ethnicity"] == "bumi_malay"].set_index("state")["population"]
            results = []
            for state in comparison_states:
                if state in overall_pops.index and state in malay_pops.index:
                    total = overall_pops[state]
                    malay = malay_pops[state]
                    results.append({"state": state, "Ethnic Groups": "Bumiputera (Malay)", "share": malay / total * 100})
                    results.append({"state": state, "Ethnic Groups": "Non-Bumiputera & Others", "share": (total - malay) / total * 100})
            if results:
                eth_df = pd.DataFrame(results)
                eth_df["state"] = pd.Categorical(eth_df["state"], categories=comparison_states, ordered=True)
                eth_df = eth_df.sort_values("state")
                fig_eth = px.bar(
                    eth_df,
                    x="state",
                    y="share",
                    color="Ethnic Groups",
                    barmode="stack",
                    labels={"state": "State", "share": "Percentage (%)"},
                    title=f"Ethnic Composition ({latest[:4]})",
                    text_auto=".1f",
                )
                fig_eth.update_layout(height=400, yaxis_range=[0, 100])
                st.plotly_chart(fig_eth, width="stretch")

    # --- GDP per capita ---
    st.markdown("#### GDP per Capita")
    try:
        gdp_df = load_gdp_state()
    except Exception:
        gdp_df = pd.DataFrame()

    if not gdp_df.empty:
        gdp_state = gdp_df[gdp_df["state"].isin(comparison_states) & (gdp_df["sector"] == "p0")].copy()
        if not gdp_state.empty:
            gdp_latest = gdp_state["date"].max()
            gdp_latest_data = gdp_state[gdp_state["date"] == gdp_latest]
            pop_latest = overall[overall["date"] == latest]
            per_capita_data = []
            for state in comparison_states:
                gdp_rec = gdp_latest_data[gdp_latest_data["state"] == state]
                pop_rec = pop_latest[pop_latest["state"] == state]
                if not gdp_rec.empty and not pop_rec.empty:
                    gdp_val = gdp_rec["value"].iloc[0] * 1_000_000
                    pop_val = pop_rec["population"].iloc[0] * 1000
                    per_capita_data.append({
                        "state": state,
                        "GDP per Capita (RM)": int(gdp_val / pop_val),
                    })
            if per_capita_data:
                gdp_pc_df = pd.DataFrame(per_capita_data)
                gdp_pc_df["state"] = pd.Categorical(gdp_pc_df["state"], categories=comparison_states, ordered=True)
                gdp_pc_df = gdp_pc_df.sort_values("state")
                cols = st.columns(len(comparison_states))
                for col, (_, row) in zip(cols, gdp_pc_df.iterrows()):
                    col.metric(row["state"], f"RM {row['GDP per Capita (RM)']:,}")


def render_kl_vital_stats(filtered_df, role: str = "guest"):
    try:
        births_df = load_births_kl()
        deaths_df = load_deaths_kl()
    except Exception:
        st.caption("Vital statistics could not be loaded.")
        return

    if births_df.empty or deaths_df.empty:
        return

    st.subheader("👶 KL Vital Statistics vs Property Demand")
    st.caption("Comparing natural population change (births - deaths) with property transactions and builds. Data: JPN/DOSM via data.gov.my and NAPIC.")

    births_total = births_df[births_df["sex"] == "both"][["date", "abs"]].rename(columns={"abs": "births"})
    deaths_total = deaths_df[deaths_df["sex"] == "both"][["date", "abs"]].rename(columns={"abs": "deaths"})
    vital = births_total.merge(deaths_total, on="date")
    vital["natural_increase"] = vital["births"] - vital["deaths"]
    vital["date"] = pd.to_datetime(vital["date"])
    vital = vital.sort_values("date")

    c1, c2, c3 = st.columns(3)
    latest_v = vital.iloc[-1]
    c1.metric(f"Live Births ({latest_v['date'].year})", f"{int(latest_v['births']):,}")
    c2.metric(f"Deaths ({latest_v['date'].year})", f"{int(latest_v['deaths']):,}")
    c3.metric("Natural Increase", f"+{int(latest_v['natural_increase']):,}" if latest_v['natural_increase'] > 0 else f"{int(latest_v['natural_increase']):,}")

    # Build property stats
    if filtered_df is not None and not filtered_df.empty:
        prop_df = filtered_df.copy()
        prop_df["_year"] = prop_df["txn_mth_id"].astype(str).str[:4]
        prop_yearly = prop_df.groupby("_year").agg(transactions=("txn_price_rm", "count")).reset_index()
        prop_yearly["date"] = pd.to_datetime(prop_yearly["_year"] + "-01-01")
        prop_yearly = prop_yearly.sort_values("date")

        combined = vital.merge(prop_yearly, on="date", how="left")

        fig_vital = px.line(
            combined.melt(id_vars=["date"], value_vars=["births", "deaths", "natural_increase", "transactions"],
                          var_name="metric", value_name="count"),
            x="date",
            y="count",
            color="metric",
            labels={"date": "Year", "count": "Count", "metric": "Metric"},
            title="KL: Natural Population Change vs Property Transactions",
        )
        fig_vital.update_layout(height=400, hovermode="x unified")
        st.plotly_chart(fig_vital, width="stretch")

        # Density and birth rate analysis
        if role == "subscribed":
            st.markdown("#### KL Property Demand Signals")
            st.caption("Key metrics linking population dynamics to housing demand")
            try:
                age_df = load_population_age_kl()
                pop_overall = age_df[(age_df["age"] == "overall") & (age_df["sex"] == "both") & (age_df["ethnicity"] == "overall")]
                latest_pop_rec = pop_overall[pop_overall["date"] == pop_overall["date"].max()]
                if not latest_pop_rec.empty:
                    kl_pop = latest_pop_rec["population"].iloc[0] * 1000
                    latest_year = str(latest_v['date'].year)
                    txn_count = prop_yearly[prop_yearly["_year"] == latest_year]["transactions"].iloc[0] if latest_year in prop_yearly["_year"].values else 0
                    birth_rate = latest_v['births'] / kl_pop * 1000
                    death_rate = latest_v['deaths'] / kl_pop * 1000
                    txn_rate = txn_count / kl_pop * 1000

                    sig_cols = st.columns(4)
                    sig_cols[0].metric("Population", f"{int(kl_pop):,}")
                    sig_cols[1].metric("Birth Rate", f"{birth_rate:.1f}/1K pop.")
                    sig_cols[2].metric("Death Rate", f"{death_rate:.1f}/1K pop.")
                    sig_cols[3].metric("Property Txn Rate", f"{txn_rate:.1f}/1K pop.")

                    avg_increase = vital["natural_increase"].mean()
                    sig_cols2 = st.columns(3)
                    sig_cols2[0].metric("Avg Annual Natural Increase", f"+{int(avg_increase):,}")
                    sig_cols2[1].metric("Txn vs Increase Ratio", f"{txn_count / avg_increase:.1f}x" if avg_increase > 0 else "N/A",
                                         help="Property transactions per unit of natural population increase")
                    sig_cols2[2].metric("KL Density", f"{int(kl_pop / 243):,}/km²", help="Population density (243 km² area)")

                    # Property demand prediction
                    hh_profile = load_hh_profile_kl()
                    if hh_profile:
                        st.markdown("#### 🔮 Property Demand Forecast")
                        st.caption("Projected extra housing units needed based on natural population increase and current persons-per-dwelling ratio. Forecast uses Monte Carlo simulation (1000 iterations) with 5%-95% confidence bands.")

                        pop_per_dwelling = kl_pop / hh_profile["living_quarters"]
                        hist_increases = vital["natural_increase"].values
                        n_years = 5
                        future_years = list(range(latest_v['date'].year + 1, latest_v['date'].year + n_years + 1))

                        rng = np.random.default_rng(42)
                        n_sims = 1000
                        sim_results = np.zeros((n_sims, n_years))
                        for i in range(n_sims):
                            cum_extra = 0
                            for j in range(n_years):
                                draw = rng.choice(hist_increases)
                                cum_extra += max(draw, 0)
                                sim_results[i, j] = cum_extra / pop_per_dwelling

                        medians = np.median(sim_results, axis=0)
                        p5 = np.percentile(sim_results, 5, axis=0)
                        p95 = np.percentile(sim_results, 95, axis=0)

                        forecast_df = pd.DataFrame({
                            "year": future_years,
                            "median": medians,
                            "p5": p5,
                            "p95": p95,
                        }).melt(id_vars=["year"], var_name="band", value_name="units")

                        fig_pred = px.line(
                            forecast_df,
                            x="year",
                            y="units",
                            color="band",
                            labels={"year": "", "units": "Cumulative Extra Housing Units Needed", "band": ""},
                            title=f"Projected Extra Housing Units Needed in KL ({future_years[0]}-{future_years[-1]})",
                        )
                        fig_pred.update_traces(line=dict(width=2), selector=dict(name="median"))
                        fig_pred.update_traces(line=dict(dash="dash", width=1), selector=dict(name="p5"))
                        fig_pred.update_traces(line=dict(dash="dash", width=1), selector=dict(name="p95"))
                        fig_pred.update_layout(
                            height=400,
                            hovermode="x unified",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        )
                        fig_pred.update_xaxes(dtick=1)
                        fig_pred.add_annotation(
                            x=future_years[-1], y=medians[-1],
                            text=f"{medians[-1]:,.0f} units",
                            showarrow=True, arrowhead=2,
                        )
                        st.plotly_chart(fig_pred, width="stretch")

                        c1, c2 = st.columns(2)
                        c1.metric("Avg Persons per Dwelling", f"{pop_per_dwelling:.2f}")
                        c2.metric("Est. Extra Units Needed (5yr)", f"{int(medians[-1]):,}",
                                  help=f"5th–95th percentile: {int(p5[-1]):,} to {int(p95[-1]):,}")

            except Exception:
                pass
        else:
            st.info("**Property Demand Signals** — including the demand forecast chart — are available to subscribed users.", icon="🔒")


@st.cache_data(show_spinner=False, ttl=3600)
def load_hh_profile_kl() -> dict | None:
    try:
        data = _fetch_json_params(
            f"{BASE_URL}/data-catalogue",
            {"id": "hh_profile_state", "ifilter": "W.P. Kuala Lumpur@state", "limit": 100},
        )
        df = pd.DataFrame(data)
        if df.empty:
            return None
        latest = df[df["date"] == df["date"].max()]
        if latest.empty:
            return None
        row = latest.iloc[0]
        return {"households": int(row["households"]), "living_quarters": int(row["living_quarters"]), "date": row["date"]}
    except Exception:
        return None


def get_poverty_for_map():
    try:
        pov_df = load_poverty_district()
    except Exception:
        return None
    kl_pov = pov_df[pov_df["state"] == "W.P. Kuala Lumpur"]
    if not kl_pov.empty:
        latest = kl_pov[kl_pov["date"] == kl_pov["date"].max()]
        if not latest.empty:
            return {
                "poverty_absolute": latest["poverty_absolute"].iloc[0],
                "poverty_relative": latest["poverty_relative"].iloc[0],
            }
    return None
