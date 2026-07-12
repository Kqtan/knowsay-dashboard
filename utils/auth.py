from __future__ import annotations

import logging
import os
import secrets
import streamlit as st
import time as _time
from typing import Any
from .supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Server-side session store — keyed by random nonce, no tokens exposed to client.
_AUTH_SESSION_TTL = 86400  # 24 hours
_AUTH_SESSION_STORE: dict[str, dict[str, Any]] = {}


def _clean_expired_sessions() -> None:
    now = _time.time()
    expired = [
        sid
        for sid, data in _AUTH_SESSION_STORE.items()
        if now - data.get("_created_at", 0) > _AUTH_SESSION_TTL
    ]
    for sid in expired:
        del _AUTH_SESSION_STORE[sid]


def _put_session(user: dict, access_token: str | None, refresh_token: str | None, role: str) -> str:
    """Store session data server-side and return a random nonce (session ID).

    Only the nonce goes to the client (in URL). The actual tokens stay in memory.
    """
    _clean_expired_sessions()
    session_id = secrets.token_urlsafe(32)
    _AUTH_SESSION_STORE[session_id] = {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": role,
        "_created_at": _time.time(),
    }
    return session_id


def _get_session(session_id: str) -> dict[str, Any] | None:
    """Retrieve a session from the store without removing it."""
    return _AUTH_SESSION_STORE.get(session_id)


def _set_sid_in_url(session_id: str | None) -> None:
    """Store only the random session nonce in the URL — no tokens."""
    # Clear any stale token params first
    for stale_key in ["auth_refresh", "auth_session"]:
        st.query_params.pop(stale_key, None)
    if session_id:
        st.query_params["sid"] = session_id
    else:
        st.query_params.pop("sid", None)


def _get_sid_from_url() -> str | None:
    params = st.query_params
    ids = params.get_all("sid")
    return ids[0] if ids else None


def _try_restore_session() -> None:
    """Restore auth from the server-side session store using the session nonce in the URL.

    The nonce survives in the URL, the real tokens stay server-side in the session store.
    Unlike the previous pop-rotate approach, the session is never deleted on read —
    it stays valid until explicitly cleared (logout) or expired (TTL).
    """
    _clean_expired_sessions()
    sid = _get_sid_from_url()
    if not sid:
        return
    data = _get_session(sid)
    if not data:
        return

    st.session_state.auth_user = data["user"]
    st.session_state.auth_access_token = data["access_token"]
    st.session_state.auth_refresh_token = data["refresh_token"]
    st.session_state.auth_role = data.get("role", "free")
    st.session_state.auth_error = None
    st.session_state.auth_login_time = data.get("_created_at")
    st.session_state.auth_email_confirmed = _is_email_confirmed(data["user"])

    logger.info("Session restored for user %s", data["user"].get("id"))


def init_auth_state() -> None:
    """Ensure Streamlit session state has auth keys initialized."""
    # Clean stale URL params from previous approaches
    for stale_key in ["auth_session", "auth_refresh"]:
        st.query_params.pop(stale_key, None)

    # Try to restore from server-side session store (handles page refreshes)
    _try_restore_session()

    for key, default in [
        ("auth_user", None),
        ("auth_access_token", None),
        ("auth_refresh_token", None),
        ("auth_role", "free"),
        ("auth_error", None),
        ("auth_page", "login"),
        ("auth_email_confirmed", False),
        ("auth_login_time", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def get_current_user() -> dict | None:
    return st.session_state.get("auth_user")


def get_current_user_role() -> str:
    return st.session_state.get("auth_role", "free")


def _user_to_dict(user) -> dict | None:
    """Convert a Supabase User object to a dictionary for consistent access."""
    if user is None:
        return None
    if isinstance(user, dict):
        return user
    # User object - convert to dict
    return {
        "id": getattr(user, "id", None),
        "email": getattr(user, "email", None),
        "user_metadata": getattr(user, "user_metadata", {}),
        "app_metadata": getattr(user, "app_metadata", {}),
        "created_at": getattr(user, "created_at", None),
        "email_confirmed_at": getattr(user, "email_confirmed_at", None),
        "confirmed_at": getattr(user, "confirmed_at", None),
    }


def _session_to_dict(session) -> dict | None:
    """Convert a Supabase Session object to a dictionary for consistent access."""
    if session is None:
        return None
    if isinstance(session, dict):
        return session
    # Session object - convert to dict
    return {
        "access_token": getattr(session, "access_token", None),
        "refresh_token": getattr(session, "refresh_token", None),
        "expires_in": getattr(session, "expires_in", None),
    }


_TOKEN_REFRESH_INTERVAL = 3300  # 55 minutes (Supabase tokens expire in 60)


def _normalize_response(response):
    if response is None:
        return None, None, None, "No response from Supabase authentication."

    error = None
    user = None
    session = None

    if isinstance(response, dict):
        error = response.get("error")
        if error is None and isinstance(response.get("data"), dict):
            data = response.get("data")
            user = data.get("user")
            session = data.get("session")
        else:
            user = response.get("user")
            session = response.get("session")
    else:
        error = getattr(response, "error", None)
        user = getattr(response, "user", None)
        session = getattr(response, "session", None)

    if error:
        if isinstance(error, dict):
            error = error.get("message") or str(error)
        else:
            error = str(error)

    # Convert User and Session objects to dictionaries
    user = _user_to_dict(user)
    session = _session_to_dict(session)

    access_token = None
    refresh_token = None
    if session and isinstance(session, dict):
        access_token = session.get("access_token")
        refresh_token = session.get("refresh_token")

    return user, access_token, refresh_token, error


def create_user_profile(user_id: str, email: str, role: str = "free", access_token: str | None = None, refresh_token: str | None = None) -> tuple[dict | None, str | None]:
    """Create a simple profile row for a new user.

    Uses the anon client with the user's JWT; the RLS policy
    ``authenticated_insert_own_profile`` allows inserting own profile.
    """
    try:
        supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
        response = supabase.schema("main").table("profiles").insert(
            {
                "user_id": user_id,
                "email": email,
                "role": role,
            }
        ).execute()
    except Exception as exc:
        return None, str(exc)

    error = getattr(response, "error", None)
    if error:
        return None, str(error)

    return getattr(response, "data", None), None


def fetch_user_profile(user_id: str, access_token: str | None = None, refresh_token: str | None = None) -> dict | None:
    """Fetch the user's role from the profiles table.

    Attaches the user's access_token so RLS sees an authenticated user.
    """
    try:
        supabase = get_supabase_client(access_token=access_token, refresh_token=refresh_token)
        response = supabase.schema("main").table("profiles").select("role").eq("user_id", user_id).single().execute()
        data = getattr(response, "data", None)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("Failed to fetch profile for user %s: %s", user_id, exc)
        return None


def _resolve_user_role(user: dict, access_token: str | None = None, refresh_token: str | None = None) -> str:
    """Determine the user's role, checking profiles table, defaulting to 'free'."""
    user_id = user.get("id")
    if user_id:
        profile = fetch_user_profile(user_id, access_token=access_token, refresh_token=refresh_token)
        if profile and profile.get("role"):
            return profile["role"]
    return "free"


def sign_up_with_email_password(email: str, password: str) -> tuple[dict | None, str | None]:
    """Register a new user with a default free role."""
    try:
        supabase = get_supabase_client()
        response: Any = supabase.auth.sign_up(
            {"email": email, "password": password},
            {"data": {"role": "free"}}
        )
    except TypeError:
        try:
            response: Any = supabase.auth.sign_up(
                {"email": email, "password": password}
            )
        except Exception as exc:
            logger.warning("Signup failed (fallback) for %s: %s", email, exc)
            return None, str(exc)
    except Exception as exc:
        logger.warning("Signup failed for %s: %s", email, exc)
        return None, str(exc)

    user, access_token, refresh_token, error = _normalize_response(response)
    if error:
        logger.warning("Signup response error for %s: %s", email, error)
        return None, error

    if not user:
        logger.warning("Signup returned no user for %s", email)
        return None, "Signup failed: no user data returned from Supabase."

    confirmed = _is_email_confirmed(user)

    user_id = user.get("id")
    if user_id:
        profile_data, profile_error = create_user_profile(user_id, email, role="free", access_token=access_token, refresh_token=refresh_token)
        if profile_error:
            logger.error("Profile creation failed for user %s: %s", user_id, profile_error)
            return None, f"Signup succeeded but profile creation failed: {profile_error}"

    logger.info("User registered: %s (role=%s, confirmed=%s)", email, "free", confirmed)

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": _resolve_user_role(user, access_token=access_token, refresh_token=refresh_token),
        "email_confirmed": confirmed,
    }, None


def login_with_email_password(email: str, password: str) -> tuple[dict | None, str | None]:
    """Authenticate with Supabase using email and password."""
    try:
        supabase = get_supabase_client()
        response: Any = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception as exc:
        logger.warning("Login failed for %s: %s", email, exc)
        return None, str(exc)

    user, access_token, refresh_token, error = _normalize_response(response)
    if error:
        logger.warning("Login rejected for %s: %s", email, error)
        return None, error

    if not user:
        logger.warning("Login failed: user not found for %s", email)
        return None, "Login failed: User Not Registered."

    confirmed = _is_email_confirmed(user)
    role = _resolve_user_role(user, access_token=access_token, refresh_token=refresh_token)

    logger.info("User logged in: %s (role=%s, confirmed=%s)", email, role, confirmed)

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": role,
        "email_confirmed": confirmed,
    }, None


def logout() -> None:
    """Clear auth session state and sign out from Supabase."""
    user = get_current_user()
    try:
        supabase = get_supabase_client()
        supabase.auth.sign_out()
    except Exception as exc:
        logger.error("Supabase sign_out failed for user %s: %s", user.get("id") if user else None, exc)

    st.session_state.auth_user = None
    st.session_state.auth_access_token = None
    st.session_state.auth_refresh_token = None
    st.session_state.auth_role = "free"
    st.session_state.auth_error = None
    st.session_state.auth_page = "login"
    sid = _get_sid_from_url()
    if sid:
        _AUTH_SESSION_STORE.pop(sid, None)
        _set_sid_in_url(None)
    logger.info("User logged out: %s", user.get("email") if user else None)


def _is_email_confirmed(user: dict) -> bool:
    return bool(
        # user.get("email_confirmed_at")
        user.get("confirmed_at")
        # or user.get("app_metadata", {}).get("email_confirmed")
        # or user.get("user_metadata", {}).get("email_confirmed")
    )


def _try_refresh_session() -> bool:
    refresh_token = st.session_state.get("auth_refresh_token")
    if not refresh_token:
        return False
    try:
        supabase = get_supabase_client()
        session = supabase.auth.refresh_session(refresh_token)
        access = (
            getattr(session, "access_token", None)
            or (session.get("access_token") if isinstance(session, dict) else None)
        )
        refresh = (
            getattr(session, "refresh_token", None)
            or (session.get("refresh_token") if isinstance(session, dict) else None)
        )
        if access:
            st.session_state.auth_access_token = access
            st.session_state.auth_refresh_token = refresh
            st.session_state.auth_login_time = _time.time()
            # Update the server-side session store so page refresh uses fresh tokens
            sid = _get_sid_from_url()
            if sid and sid in _AUTH_SESSION_STORE:
                _AUTH_SESSION_STORE[sid]["access_token"] = access
                _AUTH_SESSION_STORE[sid]["refresh_token"] = refresh
                _AUTH_SESSION_STORE[sid]["_created_at"] = _time.time()
            logger.info("Session token refreshed successfully")
            return True
    except Exception as exc:
        logger.error("Session token refresh failed: %s", exc, exc_info=True)
    return False


def ensure_valid_session() -> None:
    login_time = st.session_state.get("auth_login_time")
    if login_time and _time.time() - login_time > _TOKEN_REFRESH_INTERVAL:
        _try_refresh_session()


def send_password_reset_email(email: str) -> tuple[bool, str | None]:
    try:
        base_url = os.getenv("STREAMLIT_URL", "http://localhost:8501")
        supabase = get_supabase_client()
        supabase.auth.reset_password_email(
            email,
            options={"redirect_to": f"{base_url}/static/recovery.html"},
        )
        logger.info("Password reset email sent to %s (redirect_to=%s/static/recovery.html)", email, base_url)
    except Exception as exc:
        logger.warning("Password reset email failed for %s: %s", email, exc)
        return False, str(exc)
    return True, None


def update_password(current_password: str, new_password: str) -> tuple[bool, str | None]:
    ensure_valid_session()
    email = st.session_state.get("auth_user", {}).get("email")
    if not email:
        return False, "No authenticated user found."

    try:
        supabase = get_supabase_client()
        supabase.auth.sign_in_with_password(
            {"email": email, "password": current_password}
        )
    except Exception:
        return False, "Current password is incorrect."

    try:
        supabase = get_supabase_client(
            access_token=st.session_state.get("auth_access_token"),
            refresh_token=st.session_state.get("auth_refresh_token"),
        )
        supabase.auth.update_user({"password": new_password})
        logger.info("Password changed successfully for %s", email)
        return True, None
    except Exception as exc:
        logger.error("Password change failed for %s: %s", email, exc)
        return False, str(exc)


def reset_password(new_password: str) -> tuple[bool, str | None]:
    """Reset password using the recovery session — no current password needed.

    The recovery access_token (from the email link) is already stored in
    session state by _detect_and_handle_recovery. We use it directly to
    call update_user, bypassing the current-password check.
    """
    access_token = st.session_state.get("auth_access_token")
    if not access_token:
        return False, "No recovery session found."
    try:
        supabase = get_supabase_client(
            access_token=access_token,
            refresh_token=st.session_state.get("auth_refresh_token"),
        )
        supabase.auth.update_user({"password": new_password})
        logger.info("Password reset successfully via recovery flow")
        return True, None
    except Exception as exc:
        logger.error("Password reset via recovery failed: %s", exc)
        return False, str(exc)


def _detect_and_handle_recovery() -> bool:
    params = st.query_params
    type_list = params.get_all("type")
    if not type_list or type_list[0] != "recovery":
        return False

    access_token_list = params.get_all("access_token")
    refresh_token_list = params.get_all("refresh_token")

    if not access_token_list:
        return False

    access_token = access_token_list[0]
    refresh_token = refresh_token_list[0] if refresh_token_list else None

    # Clear recovery tokens from the URL immediately
    st.query_params.clear()

    try:
        supabase = get_supabase_client(
            access_token=access_token,
            refresh_token=refresh_token,
        )
        auth_response = supabase.auth.get_user()
        user = _user_to_dict(getattr(auth_response, "user", None))
        if not user:
            logger.warning("Recovery: no user found for provided tokens")
            return False

        role = _resolve_user_role(user, access_token=access_token, refresh_token=refresh_token)

        st.session_state.auth_user = user
        st.session_state.auth_access_token = access_token
        st.session_state.auth_refresh_token = refresh_token
        st.session_state.auth_role = role
        st.session_state.auth_error = None
        st.session_state.auth_page = "reset_password"
        st.session_state.auth_login_time = _time.time()
        st.session_state.auth_email_confirmed = _is_email_confirmed(user)

        sid = _put_session(user, access_token, refresh_token, role)
        _set_sid_in_url(sid)
        logger.info("Recovery session established for user %s", user.get("id"))
        return True
    except Exception as exc:
        logger.error("Recovery handler failed: %s", exc, exc_info=True)
        return False


def render_reset_password_page() -> None:
    current_user = get_current_user()
    user_email = current_user.get("email") or current_user.get("user_metadata", {}).get("email", "") if current_user else ""
    username = user_email.split("@")[0] if user_email else "user"
    is_recovery = st.session_state.get("auth_page") == "reset_password"

    st.title("🔐 Reset Your Password")
    st.markdown(f"Logged in as **{user_email}**")
    if is_recovery:
        st.markdown("Choose a new password for your account.")
    else:
        st.markdown("Enter your current password and choose a new one.")

    with st.form("reset_password_form"):
        current_password = st.text_input("Current Password", type="password") if not is_recovery else None
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Reset Password", width='stretch')

        if submitted:
            if not new_password:
                st.error("New password is required.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            elif not is_recovery and not current_password:
                st.error("Current password is required.")
            elif not is_recovery and new_password == current_password:
                st.error("New password must be different from current password.")
            else:
                if is_recovery:
                    _, error = reset_password(new_password)
                else:
                    _, error = update_password(current_password, new_password)
                if error:
                    st.session_state.auth_error = error
                else:
                    st.session_state.auth_page = "login"
                    st.session_state.auth_error = None
                    st.success("Password reset successfully! Redirecting to login...")
                    st.rerun()

    if st.session_state.auth_error:
        st.error(st.session_state.auth_error)


def render_auth_sidebar() -> None:
    """Render login/logout controls in the Streamlit sidebar."""
    init_auth_state()
    _try_restore_session()
    _detect_and_handle_recovery()

    current_user = get_current_user()

    # Logged-in reset password flow (from recovery email)
    if current_user and st.session_state.get("auth_page") == "reset_password":
        user_email = current_user.get("email") or current_user.get("user_metadata", {}).get("email", "")
        username = user_email.split("@")[0] if user_email else "user"
        st.sidebar.title(f"👋 Hello there, {username}")
        st.sidebar.info("Use the reset form on the main page to set a new password.")
        if st.sidebar.button("Logout"):
            logout()
            st.rerun()
        return

    # Normal logged-in view
    if current_user:
        user_email = current_user.get("email") or current_user.get("user_metadata", {}).get("email", "")
        username = user_email.split("@")[0] if user_email else "user"
        st.sidebar.title(f"👋 Hello there, {username}")
        if user_email:
            st.sidebar.success(f"Signed in as {user_email}")
        else:
            st.sidebar.success("Signed in")

        if not st.session_state.get("auth_email_confirmed", False):
            st.sidebar.warning(
                "Email not confirmed. Please check your inbox and verify your email address to access all features."
            )

        if st.sidebar.button("Logout"):
            logout()
            st.rerun()

        st.sidebar.caption("Use logout before leaving the app to clear auth state.")
        return

    # Forgot password form
    if st.session_state.get("auth_page") == "forgot_password":
        st.sidebar.title("🔐 Reset Password")
        st.sidebar.markdown("Password recovery is temporarily unavailable.")

        with st.sidebar.form("forgot_password_form"):
            email = st.text_input("Email", key="forgot_email")
            submitted = st.form_submit_button("Send Reset Link", disabled=True)

            if submitted:
                if not email:
                    st.sidebar.error("Email is required.")
                else:
                    _, error = send_password_reset_email(email.strip())
                    if error:
                        st.session_state.auth_error = error
                    else:
                        st.sidebar.success("Password reset email sent! Check your inbox.")
                        st.session_state.auth_error = None

        if st.sidebar.button("← Back to Login"):
            st.session_state.auth_page = "login"
            st.session_state.auth_error = None
            st.rerun()

        if st.session_state.auth_error:
            st.sidebar.error(st.session_state.auth_error)
        return

    # Default: Login / Register tabs
    st.sidebar.title("🔐 KnowSay")

    tab_login, tab_register = st.sidebar.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            st.write("Sign in to KnowSay")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")

            if submitted:
                if not email or not password:
                    st.sidebar.error("Email and password are required.")
                else:
                    auth_data, auth_error = login_with_email_password(email.strip(), password)
                    if auth_error:
                        logger.warning("Login failed for %s: %s", email.strip(), auth_error)
                        st.session_state.auth_error = auth_error
                    else:
                        st.session_state.auth_user = auth_data["user"]
                        st.session_state.auth_access_token = auth_data["access_token"]
                        st.session_state.auth_refresh_token = auth_data["refresh_token"]
                        st.session_state.auth_role = auth_data.get("role", "free")
                        st.session_state.auth_email_confirmed = auth_data.get("email_confirmed", False)
                        st.session_state.auth_login_time = _time.time()
                        st.session_state.auth_error = None
                        sid = _put_session(
                            auth_data["user"],
                            auth_data["access_token"],
                            auth_data["refresh_token"],
                            st.session_state.auth_role,
                        )
                        _set_sid_in_url(sid)
                        st.rerun()

        if st.button("Forgot Password?", key="forgot_link"):
            st.session_state.auth_page = "forgot_password"
            st.session_state.auth_error = None
            st.rerun()

    with tab_register:
        with st.form("register_form", clear_on_submit=False):
            st.write("Create a free account. Subscribe anytime to unlock the full picture.")
            register_email = st.text_input("Email", key="register_email")
            register_password = st.text_input("Password", type="password", key="register_password")
            register_submit = st.form_submit_button("Register", disabled=True)

            if register_submit:
                if not register_email or not register_password:
                    st.sidebar.error("Email and password are required for registration.")
                else:
                    auth_data, auth_error = sign_up_with_email_password(register_email.strip(), register_password)
                    if auth_error:
                        logger.warning("Registration failed for %s: %s", register_email.strip(), auth_error)
                        st.session_state.auth_error = auth_error
                    else:
                        st.session_state.auth_user = auth_data["user"]
                        st.session_state.auth_access_token = auth_data["access_token"]
                        st.session_state.auth_refresh_token = auth_data["refresh_token"]
                        st.session_state.auth_role = auth_data.get("role", "free")
                        st.session_state.auth_email_confirmed = auth_data.get("email_confirmed", False)
                        st.session_state.auth_login_time = _time.time()
                        st.session_state.auth_error = None
                        sid = _put_session(
                            auth_data["user"],
                            auth_data["access_token"],
                            auth_data["refresh_token"],
                            st.session_state.auth_role,
                        )
                        _set_sid_in_url(sid)
                        st.sidebar.success("Registration successful. You are now signed in as a free user.")
                        st.rerun()

    if st.session_state.auth_error:
        st.sidebar.error(st.session_state.auth_error)


def require_auth() -> None:
    """Stop app execution if the user is not authenticated or email not confirmed."""
    if not get_current_user():
        st.warning("Please log in via the left panel in the sidebar to access KnowSay.")
        st.stop()
    if not st.session_state.get("auth_email_confirmed", False):
        st.warning(
            "Your email address has not been confirmed yet. "
            "Please check your inbox (and spam folder) for the confirmation email "
            "and click the link to verify your account before accessing KnowSay."
        )
        st.info("Once confirmed, log out and log back in to refresh your session.")
        st.stop()
