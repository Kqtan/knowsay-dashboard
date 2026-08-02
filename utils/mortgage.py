import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def calculate_mortgage_schedule(
    property_price: float,
    downpayment_amount: float,
    additional_financing: float,
    mortgage_years: int,
    annual_interest_rate: float,
) -> tuple[pd.DataFrame, dict]:
    """Build a monthly amortization schedule and headline mortgage metrics."""
    loan_amount = max(property_price - downpayment_amount + additional_financing, 0)
    total_months = max(int(mortgage_years) * 12, 1)
    monthly_rate = max(annual_interest_rate, 0) / 100 / 12

    if loan_amount == 0:
        monthly_payment = 0
    elif monthly_rate == 0:
        monthly_payment = loan_amount / total_months
    else:
        monthly_payment = (
            loan_amount
            * monthly_rate
            * (1 + monthly_rate) ** total_months
            / ((1 + monthly_rate) ** total_months - 1)
        )

    balance = loan_amount
    rows = []
    cumulative_principal = 0
    cumulative_interest = 0

    for month in range(1, total_months + 1):
        interest_payment = balance * monthly_rate
        principal_payment = min(monthly_payment - interest_payment, balance)
        if month == total_months:
            principal_payment = balance
            monthly_total = principal_payment + interest_payment
        else:
            monthly_total = monthly_payment

        balance = max(balance - principal_payment, 0)
        cumulative_principal += principal_payment
        cumulative_interest += interest_payment

        rows.append(
            {
                "Year": int(math.ceil(month / 12)),
                "Month": month,
                "Payment (RM)": monthly_total,
                "Principal (RM)": principal_payment,
                "Interest (RM)": interest_payment,
                "Cumulative Principal (RM)": cumulative_principal,
                "Cumulative Interest (RM)": cumulative_interest,
                "Remaining Balance (RM)": balance,
            }
        )

    schedule = pd.DataFrame(rows)
    metrics = {
        "loan_amount": loan_amount,
        "monthly_payment": monthly_payment,
        "total_payment": schedule["Payment (RM)"].sum() if len(schedule) else 0,
        "total_interest": schedule["Interest (RM)"].sum() if len(schedule) else 0,
    }
    return schedule, metrics


def format_rm_input(value: float) -> str:
    """Format a ringgit amount for readable form inputs."""
    return f"{float(value):,.0f}"


def parse_rm_input(value: str) -> float:
    """Parse a comma-formatted ringgit input."""
    cleaned = str(value).replace(",", "").replace("RM", "").strip()
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def render_metric_card(title: str, value: str, caption: str, tone: str = "light") -> None:
    """Render a compact dashboard-style metric card."""
    tones = {
        "primary": ("#4f63ff", "#ffffff", "rgba(255,255,255,0.72)", "rgba(255,255,255,0.22)"),
        "green": ("#65b456", "#ffffff", "rgba(255,255,255,0.74)", "rgba(255,255,255,0.22)"),
        "gray": ("#f8fafc", "#172033", "#64748b", "#eef2f7"),
        "light": ("#ffffff", "#172033", "#64748b", "#eef2f7"),
    }
    bg, fg, muted, icon_bg = tones.get(tone, tones["light"])
    shadow = "0 10px 24px rgba(15, 23, 42, 0.12)" if tone in {"light", "gray"} else "0 10px 24px rgba(15, 23, 42, 0.18)"
    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{fg};
            border-radius:8px;
            padding:1rem;
            min-height:132px;
            box-shadow:{shadow};
            border:1px solid rgba(226,232,240,0.9);
            display:flex;
            flex-direction:column;
            justify-content:space-between;
        ">
            <div style="
                width:28px;
                height:28px;
                border-radius:7px;
                background:{icon_bg};
                display:flex;
                align-items:center;
                justify-content:center;
                font-size:0.95rem;
            ">🧮</div>
            <div>
                <div style="font-size:1.55rem; font-weight:800; line-height:1.15;">{value}</div>
                <div style="font-size:0.9rem; color:{muted}; margin-top:0.15rem;">{title}</div>
            </div>
            <div style="font-size:0.78rem; color:{muted}; text-align:right;">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mortgage_calculator(median_kl_price: float | None = None):
    """Render a mortgage calculator tab with amortization charts and schedule."""
    st.subheader("Mortgage Calculator")

    defaults = {
        "property_price": 600_000.0,
        "downpayment_mode": "RM",
        "downpayment_rm": 60_000.0,
        "downpayment_pct": 10,
        "additional_financing": 20_000.0,
        "mortgage_years": 35,
        "annual_interest_rate": 3.75,
    }
    if "mortgage_inputs" not in st.session_state:
        st.session_state.mortgage_inputs = defaults.copy()

    saved_inputs = st.session_state.mortgage_inputs
    if st.session_state.pop("normalize_mortgage_inputs", False):
        st.session_state.mortgage_property_price_input = format_rm_input(saved_inputs["property_price"])
        st.session_state.mortgage_downpayment_rm_input = format_rm_input(saved_inputs["downpayment_rm"])
        st.session_state.mortgage_additional_financing_input = format_rm_input(saved_inputs["additional_financing"])

    if "mortgage_downpayment_mode_selector" not in st.session_state:
        st.session_state.mortgage_downpayment_mode_selector = saved_inputs["downpayment_mode"]

    downpayment_mode = st.radio(
        "Downpayment input",
        options=["RM", "%"],
        horizontal=True,
        key="mortgage_downpayment_mode_selector",
    )

    with st.form("mortgage_calculator_form"):
        input_col, summary_col = st.columns([1, 1], gap="large")

        with input_col:
            property_price_text = st.text_input(
                "Property price (RM)",
                value=format_rm_input(saved_inputs["property_price"]),
                key="mortgage_property_price_input",
            )
            property_price_preview = parse_rm_input(property_price_text)

            if downpayment_mode == "RM":
                downpayment_amount_text = st.text_input(
                    "Downpayment (RM)",
                    value=format_rm_input(saved_inputs["downpayment_rm"]),
                    key="mortgage_downpayment_rm_input",
                )
                downpayment_amount_input = parse_rm_input(downpayment_amount_text)
                downpayment_percent_input = int(round(
                    downpayment_amount_input / property_price_preview * 100
                )) if property_price_preview else 0
            else:
                downpayment_percent_input = st.number_input(
                    "Downpayment (%)",
                    min_value=0,
                    max_value=100,
                    value=int(saved_inputs["downpayment_pct"]),
                    step=1,
                    format="%d",
                    key="mortgage_downpayment_pct_input",
                )
                downpayment_amount_input = property_price_preview * downpayment_percent_input / 100

            additional_financing_text = st.text_input(
                "MRTA and others, if financed (RM)",
                value=format_rm_input(saved_inputs["additional_financing"]),
                key="mortgage_additional_financing_input",
            )
            mortgage_years = st.number_input(
                "Length of mortgage (years)",
                min_value=1,
                max_value=45,
                value=int(saved_inputs["mortgage_years"]),
                step=1,
                key="mortgage_years_input",
            )
            annual_interest_rate = st.number_input(
                "Annual interest rate (%)",
                min_value=0.0,
                value=float(saved_inputs["annual_interest_rate"]),
                step=0.05,
                format="%.2f",
                key="mortgage_interest_rate_input",
                help="Default is SBR 2.75% + 1.00%.",
            )

            submitted = st.form_submit_button("Calculate", width="stretch", type="primary")

        with summary_col:
            st.info("Change the inputs, then click Calculate to update the results.")
            if median_kl_price and median_kl_price > 0:
                st.caption(f"KL median house price reference: RM {median_kl_price:,.0f}")

    if submitted:
        property_price = parse_rm_input(property_price_text)
        additional_financing = parse_rm_input(additional_financing_text)
        if downpayment_mode == "RM":
            downpayment_amount_input = min(parse_rm_input(downpayment_amount_text), property_price)
            downpayment_percent_input = int(round(
                downpayment_amount_input / property_price * 100
            )) if property_price else 0
        else:
            downpayment_amount_input = property_price * downpayment_percent_input / 100

        st.session_state.mortgage_inputs = {
            "property_price": property_price,
            "downpayment_mode": downpayment_mode,
            "downpayment_rm": downpayment_amount_input,
            "downpayment_pct": downpayment_percent_input,
            "additional_financing": additional_financing,
            "mortgage_years": mortgage_years,
            "annual_interest_rate": annual_interest_rate,
        }
        st.session_state.normalize_mortgage_inputs = True
        st.rerun()

    saved_inputs = st.session_state.mortgage_inputs
    property_price = float(saved_inputs["property_price"])
    downpayment_amount = float(saved_inputs["downpayment_rm"])
    downpayment_percent = float(saved_inputs["downpayment_pct"])
    additional_financing = float(saved_inputs["additional_financing"])
    mortgage_years = int(saved_inputs["mortgage_years"])
    annual_interest_rate = float(saved_inputs["annual_interest_rate"])

    schedule, metrics = calculate_mortgage_schedule(
        property_price,
        downpayment_amount,
        additional_financing,
        mortgage_years,
        annual_interest_rate,
    )

    if median_kl_price and median_kl_price > 0:
        difference_pct = (property_price - median_kl_price) / median_kl_price * 100
        direction = "higher" if difference_pct >= 0 else "lower"
        median_caption = f"{abs(difference_pct):.1f}% {direction} than KL median"
    else:
        median_caption = "KL median unavailable"

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        render_metric_card("Monthly Payment", f"RM {metrics['monthly_payment']:,.0f}", median_caption, "primary")
    with sc2:
        render_metric_card("Loan Amount", f"RM {metrics['loan_amount']:,.0f}", f"{mortgage_years} years at {annual_interest_rate:.2f}%", "light")
    with sc3:
        render_metric_card("Total Payment Needed", f"RM {metrics['total_payment']:,.0f}", "Principal plus interest", "green")
    with sc4:
        render_metric_card("Total Interest Paid", f"RM {metrics['total_interest']:,.0f}", f"Downpayment RM {downpayment_amount:,.0f} ({downpayment_percent:.0f}%)", "gray")

    st.markdown("---")
    chart_col, pie_col = st.columns([2, 1], gap="large")

    yearly = (
        schedule.groupby("Year", as_index=False)[["Principal (RM)", "Interest (RM)"]]
        .sum()
    )

    with chart_col:
        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=yearly["Year"],
                y=yearly["Principal (RM)"],
                mode="lines+markers",
                name="Principal",
            )
        )
        fig_line.add_trace(
            go.Scatter(
                x=yearly["Year"],
                y=yearly["Interest (RM)"],
                mode="lines+markers",
                name="Interest",
            )
        )
        fig_line.update_layout(
            title="Annual Principal vs Interest",
            xaxis_title="Year",
            yaxis_title="Amount (RM)",
            height=430,
            hovermode="x unified",
        )
        st.plotly_chart(fig_line, width="stretch")

    with pie_col:
        fig_pie = px.pie(
            values=[metrics["loan_amount"], metrics["total_interest"]],
            names=["Principal", "Interest"],
            title="Total Principal vs Interest",
            hole=0.35,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(height=430)
        st.plotly_chart(fig_pie, width="stretch")

    st.subheader("Loan Schedule")
    display_schedule = schedule.copy()
    for column in [
        "Payment (RM)",
        "Principal (RM)",
        "Interest (RM)",
        "Cumulative Principal (RM)",
        "Cumulative Interest (RM)",
        "Remaining Balance (RM)",
    ]:
        display_schedule[column] = display_schedule[column].map(lambda value: f"RM {value:,.2f}")

    st.dataframe(display_schedule, width="stretch", hide_index=True)
