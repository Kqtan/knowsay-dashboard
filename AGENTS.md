# KnowSay — AGENTS.md

## Commands

- **Install**: `uv sync --group dev`
- **Run**: `uv run streamlit run main.py`
- **Test**: `uv run pytest -v --tb=short`
- **Lint/typecheck**: None configured

## Architecture

- **`main.py`** — Streamlit app entrypoint. Calls `init_auth_state()`, `render_auth_sidebar()`, `require_auth()` (in that order) before the dashboard. Session auth nonce lives in `?sid=` URL param. Data tab **removed** (was the main raw-data leak). Mukim map passes `role` for dataframe gating.
- **`utils/auth.py`** — Supabase email/password auth with role gating (`free` / `subscribed`). `_AUTH_SESSION_STORE` is a process-global dict; fine on Community Cloud (one user per process). `create_user_profile()` now uses anon client + user JWT (RLS policy allows inserting own profile). Service key removed.
- **`utils/supabase_client.py`** — Single client: `get_supabase_client()` (anon key + RLS via optional JWT). `get_supabase_service_client()` removed.
- **`utils/data_loader.py`** — Role-aware table selection: subscribed → `property_master_kl`, free → `property_free_v` (limited view created in Supabase). `@st.cache_data` cache key includes `role`.
- **`utils/data_gov_my.py`** — `@st.cache_data(ttl=3600)` fetchers from `api.data.gov.my`. Runs even without auth — will raise on network errors.
- **`utils/mukim_map.py`** — Choropleth using `geo_data/kl_mukims_official.geojson` (DOSM boundaries). Uses `featureidkey="properties.district"`. `render_mukim_map()` accepts `role` param; dataframe gated behind subscription.
- **Data**: CSV files in `data/` are local exports; the live app queries Supabase.

## Streamlit conventions (this repo)

- `use_container_width=True` → `width='stretch'`
- `use_container_width=False` → `width='content'`
- Chart gating: `render_gated_chart(role, fig, name, fake_fig_fn=...)` blurs content for free/guest users
- Form keys use `snake_case` with explicit `key=` to avoid duplicates on rerun
- `st.cache_data(show_spinner=False, ttl=...)` for API fetches

## Testing

- Tests are in `tests/test_main.py`, plain pytest. Mock `st.plotly_chart` / `st.markdown` directly. No fixtures.
- Tests cannot run without `.env` because `load_property_data` connects to Supabase at import time (via `st.cache_data` registration).
- CI runs `uv run pytest -v --tb=short` on push/PR to `main`.

## Important quirks

- `.env` contains `SUPABASE_SERVICE_KEY` — do **not** commit. `.streamlit/secrets.toml` is also gitignored. Service key is no longer used by the app (removed in favour of RLS policies + RPC functions).
- `SECURITY_AUDIT_FINDINGS.md` documents 11 security issues (critical: tokens in URL, global session store, no CSRF in recovery). Many have been partially fixed — verify before applying old guidance.
- `view.json` is empty; appears unused.

## Security hardening (Jul 2026)

### Supabase RLS setup (run in SQL Editor)
- Created `main.property_free_v` view (limited columns, no `scheme_name`/`road_name`)
- Enabled RLS on `main.property_master_kl` with `authenticated_read` policy
- Added `authenticated_insert_own_profile` policy on `main.profiles` (users can insert own row)

### Python changes
- Removed Data tab entirely (was showing 100 raw rows to all authenticated users)
- Gated mukim map dataframe behind subscription check
- `load_property_data()` now selects `property_free_v` for free users, `property_master_kl` for subscribed
- `create_user_profile()` uses anon client + user JWT instead of service key
- Removed `get_supabase_service_client()` from codebase entirely
- `SUPABASE_SERVICE_KEY` deleted from `.env` (commented out)
