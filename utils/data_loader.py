import logging
import pandas as pd
import streamlit as st
from .auth import ensure_valid_session
from .supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


@st.cache_data(show_spinner=False)
def load_property_data(access_token: str | None = None, role: str | None = None) -> pd.DataFrame:
    """Load dashboard data from Supabase and cache it in Streamlit."""
    try:
        ensure_valid_session()
    except Exception as exc:
        logger.error("Session validation failed in load_property_data: %s", exc, exc_info=True)
        return pd.DataFrame()

    token = st.session_state.get("auth_access_token") or access_token

    is_subscribed = role and role.lower() not in {"free", "guest", ""}
    table = "property_master_kl" if is_subscribed else "property_free_v"

    try:
        supabase = get_supabase_client()
        supabase.postgrest.auth(token=token)
        response = supabase.schema("main").table(table).select("*").execute()
    except Exception as exc:
        logger.error("Supabase query failed for table=%s: %s", table, exc, exc_info=True)
        st.error(f"Failed to load property data. Please try refreshing the page or logging in again.")
        return pd.DataFrame()

    if response.data == []:
        logger.warning("Supabase returned empty data for table=%s", table)
        return pd.DataFrame()

    data = getattr(response, "data", None)
    if data is None:
        logger.warning("Supabase returned no data attribute for table=%s", table)
        return pd.DataFrame()

    return pd.DataFrame(data)
