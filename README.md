# KnowSay

Property and economic data dashboard for Malaysia. Built with Streamlit + Supabase.

## Features

- **Property data**: Transaction prices, property types, mukim-level analysis
- **Interactive maps**: KL mukim choropleth with price per sqft
- **Market context**: Population, income, Gini, poverty, expenditure from data.gov.my
- **Affordability insights**: Price-to-income ratios, transactions-per-capita
- **Socioeconomic data**: GDP, crime, schools, demographics, vital statistics
- **Auth**: Email/password with role gating (free / subscribed tiers)

## Tech stack

- Python, Streamlit, Plotly, pandas
- Supabase (Postgres + REST API)
- [data.gov.my](https://data.gov.my) open data API

## Local development

```bash
uv sync --group dev
# copy .env with SUPABASE_URL, SUPABASE_KEY, STREAMLIT_URL
uv run streamlit run main.py
```

## Deploy to Streamlit Cloud

Set these secrets in the dashboard:

| Key | Description |
|-----|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/public key |
| `STREAMLIT_URL` | Your app URL (e.g. `https://app.streamlit.app`) |
