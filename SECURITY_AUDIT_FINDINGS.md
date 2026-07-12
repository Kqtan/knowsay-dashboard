# Security Audit Findings — KnowSay

The following findings were identified in `utils/auth.py`, `utils/supabase_client.py`, and `utils/data_loader.py`. Each finding is written as an independent instruction block that another LLM can read and implement as a code change.

---

## Finding 1: Refresh Token Exposed in URL Query Parameters

**Files:** `utils/auth.py` lines 85–100, 128, 194, 437  
**Severity:** Critical

**Problem:**
```python
# auth.py:85-100
def _set_query_refresh_token(token: str | None) -> None:
    if token:
        st.query_params["auth_refresh"] = token

# auth.py:128
def _save_auth_session(...):
    _set_query_refresh_token(refresh_token)

# auth.py:194
def _try_restore_from_query_refresh_token():
    st.session_state.auth_refresh_token = new_refresh
    _set_query_refresh_token(refresh)

# auth.py:437
def _try_refresh_session():
    st.session_state.auth_refresh_token = refresh
    _set_query_refresh_token(refresh)
```

The refresh token (a long-lived credential that can mint new access tokens) is written into `st.query_params["auth_refresh"]`. This places it in the browser's URL bar, where it is leaked via:
- HTTP Referer headers when the page links to any external resource
- Browser history and sync services
- Proxy and server access logs
- Shoulder surfing and screen sharing

**Fix instructions:**

1. Remove the functions `_set_query_refresh_token()` and `_get_query_refresh_token()` entirely.
2. Remove the call to `_set_query_refresh_token()` from `_save_auth_session()`, `_try_restore_from_query_refresh_token()`, and `_try_refresh_session()`.
3. Remove the call to `_set_query_refresh_token(None)` from `logout()`.
4. Store the refresh token **only** in `st.session_state["auth_refresh_token"]` — never serialize it to the client URL.
5. Remove the `_try_restore_from_query_refresh_token()` fallback logic entirely, or replace it with a mechanism that does not expose tokens in the URL (e.g., a server-side session store keyed by a short-lived random nonce).

---

## Finding 2: Auth Session ID in URL + Shared Global In-Memory Session Store

**Files:** `utils/auth.py` lines 73, 76–89, 131–152, 201  
**Severity:** Critical

**Problem:**
```python
# auth.py:73
AUTH_SESSION_STORE: dict[str, dict[str, Any]] = {}

# auth.py:76-80
def _get_query_session_id() -> str | None:
    params = st.query_params
    session_ids = params.get("auth_session", [])
    return session_ids[0] if session_ids else None

# auth.py:83-89
def _set_query_session_id(session_id: str | None) -> None:
    if session_id:
        st.query_params["auth_session"] = session_id
    else:
        st.query_params.clear()

# auth.py:131-149
def _restore_auth_session_from_query() -> None:
    _clean_expired_sessions()
    if get_current_user():
        return
    session_id = _get_query_session_id()
    if not session_id:
        return
    data = AUTH_SESSION_STORE.get(session_id)
    if data:
        st.session_state.auth_user = data["user"]
        ...
```

Two compounded problems:

1. `AUTH_SESSION_STORE` is a **module-level dictionary** shared across all users of the same Streamlit process. If User A obtains User B's `auth_session` query param (leaked via URL sharing, logs, Referer header), they can hijack User B's entire session by setting `?auth_session=<stolen_id>`.

2. The session ID is placed in `st.query_params["auth_session"]`, meaning it lives in the browser URL bar with all the same leak risks as Finding 1.

**Fix instructions:**

1. Delete the `AUTH_SESSION_STORE` global dict entirely.
2. Delete `_get_query_session_id()`, `_set_query_session_id()`, `_save_auth_session()`, `_clean_expired_sessions()`, `_restore_auth_session_from_query()`, and `_try_restore_from_query_refresh_token()`.
3. Rely **solely** on `st.session_state` for session persistence. Streamlit's `st.session_state` is already per-user and server-side — there is no need for a second in-memory store.
4. Remove all calls to `_save_auth_session()`, `_set_query_session_id()`, and `_restore_auth_session_from_query()` from `sign_up_with_email_password`, `login_with_email_password`, `_detect_and_handle_recovery`, and `render_auth_sidebar`.
5. Remove the `st.session_state.auth_session_id` key entirely — it is unused once the global store is removed.
6. In `logout()`, remove the `AUTH_SESSION_STORE.pop(session_id, None)` line and the `_set_query_session_id(None)` line.

---

## Finding 3: Password Recovery Handler Accepts Arbitrary Tokens from URL Without Validation

**Files:** `utils/auth.py` lines 472–517  
**Severity:** Critical

**Problem:**
```python
# auth.py:472-517
def _detect_and_handle_recovery() -> bool:
    params = st.query_params
    type_list = params.get("type", [])
    if not type_list or type_list[0] != "recovery":
        return False

    access_token_list = params.get("access_token", [])
    refresh_token_list = params.get("refresh_token", [])

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
            return False
        ...
        st.session_state.auth_user = user
        st.session_state.auth_access_token = access_token
        st.session_state.auth_refresh_token = refresh_token
        ...
        return True
    except Exception:
        return False
```

The recovery handler:
- Reads `access_token` and `refresh_token` directly from URL query params with no state/nonce verification
- Calls `supabase.auth.get_user()` with those tokens — if the tokens are valid for **any** user, it logs that user in
- Has no CSRF protection
- Has no confirmation step before setting the session
- Swallows all exceptions silently

An attacker who intercepts a recovery email link, or who crafts a URL with any valid JWT they possess, can hijack a session.

**Fix instructions:**

1. Generate a random `state` parameter when sending the password reset email via Supabase. Store it in `st.session_state`. When the user is redirected back, verify that the `state` query param matches the stored value.
2. After calling `supabase.auth.get_user()` with the recovery tokens, verify that the returned user's `email_confirmed_at` is not null and that the token's `type` claim is actually `"recovery"` (not just the URL query param).
3. Remove the `except Exception: return False` — log the error instead.
4. Do NOT store `access_token` and `refresh_token` from recovery in `st.session_state` permanently. Instead, redirect the user to a fresh login flow, or at minimum re-issue new tokens via `supabase.auth.refresh_session()` so the recovery tokens are not reused.
5. Add rate limiting: max 3 recovery attempts per email per 15 minutes.

---

## Finding 4: Silent Exception Swallowing in All Critical Auth Paths

**Files:** `utils/auth.py` lines 203–204, 439–440, 516–517  
**Severity:** High

**Problem:**
```python
# auth.py:203-204
    except Exception:
        pass

# auth.py:439-440
    except Exception:
        pass

# auth.py:516-517
    except Exception:
        return False

# auth.py:379-381
    except Exception:
        pass
```

Every authentication-related exception is swallowed with a bare `except: pass` or `except: return False`. This means:
- Failed token refreshes are invisible — users silently lose access
- Attackers can probe the auth system without generating any alerts
- Supabase outages cause silent failures with no user feedback
- No forensic data exists for incident response

**Fix instructions:**

1. Replace every bare `except Exception: pass` in `utils/auth.py` with:
   ```python
   except Exception as exc:
       import logging
       logging.error("Auth error in %s: %s", __name__, str(exc), exc_info=True)
       st.session_state.auth_error = str(exc)
   ```
   (at minimum — structured logging with `structlog` or similar is better).

2. In `_try_refresh_session()` and `_try_restore_from_query_refresh_token()`, return the error message to the caller so the UI can show feedback.

3. In `logout()`, log the exception but don't block the user from being logged out locally (the local state clearing should still happen).

4. Add an `import logging` at the top of `utils/auth.py`.

5. Configure logging in `main.py` or `utils/supabase_client.py` to output to stderr or a log file:
   ```python
   logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
   ```

---

## Finding 5: Rate Limiting Is In-Memory, Per-Process, and Keyed Only by Email

**Files:** `utils/auth.py` lines 67–72, 398–406  
**Severity:** High

**Problem:**
```python
# auth.py:67-72
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW = 900  # 15 minutes
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}

# auth.py:398-406
def _check_rate_limit(email: str) -> bool:
    now = _time.time()
    attempts = _LOGIN_ATTEMPTS.get(email, [])
    attempts = [t for t in attempts if now - t < _LOGIN_WINDOW]
    _LOGIN_ATTEMPTS[email] = attempts
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        return False
    attempts.append(now)
    return True
```

Three issues:
1. `_LOGIN_ATTEMPTS` is a **process-global dict** — rate limiting resets on every server restart and does not work across multiple Streamlit instances.
2. Rate limiting is keyed **only by email**, not by IP address. An attacker with a list of 6 valid emails can make unlimited attempts.
3. The login and signup functions share the same `_check_rate_limit()` function, so hitting the limit on one blocks the other.

**Fix instructions:**

1. Remove the `_LOGIN_ATTEMPTS` dict and `_check_rate_limit()` function.
2. Use **Supabase's built-in rate limiting** (Supabase Auth already rate-limits by IP by default) — this is more reliable and doesn't require custom code.
3. As a defense-in-depth layer, add IP-based rate limiting using the request IP:
   ```python
   import streamlit as st
   # Streamlit doesn't expose the client IP directly,
   # but you can use st.server.server.get_client_ip() or proxy headers
   ```
   Or implement a lightweight rate limiter using `st.session_state` with TTL (though this is still per-user and resets on refresh).
4. If you keep a custom rate limiter, key it by **both** IP address and email, and use a shared store (Redis/memcached) instead of a global dict.
5. Add exponential backoff: after 5 failures, lock for 15 min; after 10, lock for 1 hour; after 20, lock for 24 hours.
6. Add CAPTCHA (e.g., hCaptcha or Turnstile) after 3 failed attempts from the same IP.

---

## Finding 7: Email Confirmation Check Is Only at the Application Layer, Not the Data Layer

**Files:** `utils/auth.py` lines 409–415, 695–699; `main.py` lines 204–211  
**Severity:** High

**Problem:**
```python
# auth.py:695-699
def require_auth() -> None:
    """Stop app execution if the user is not authenticated."""
    if not get_current_user():
        st.warning("...")
        st.stop()

# main.py:204-211
    if not st.session_state.get("auth_email_confirmed", False):
        st.warning("...")
        st.stop()
```

`require_auth()` only checks if a user object exists in session state — it does **not** check email confirmation. The email-confirmed check is in `main.py` as a separate block that can be easily missed when adding new pages/routes. Any new page that calls `require_auth()` but forgets the email confirmation check will allow unconfirmed users through.

**Fix instructions:**

1. Move the email confirmation check **into `require_auth()`** so every protected page automatically enforces it:
   ```python
   def require_auth() -> None:
       if not get_current_user():
           st.warning("Please log in via the left panel in the sidebar to access the dashboard.")
           st.stop()
       if not st.session_state.get("auth_email_confirmed", False):
           st.warning(
               "Your email address has not been confirmed yet. "
               "Please check your inbox (and spam folder) for the confirmation email "
               "and click the link to verify your account before accessing the dashboard."
           )
           st.info("Once confirmed, log out and log back in to refresh your session.")
           st.stop()
   ```
2. Remove the separate email confirmation check block from `main.py` lines 204–211, since `require_auth()` now handles it.
3. For defense-in-depth, add a **Supabase RLS policy** that checks `auth.jwt()->>'email_confirmed'` or a custom claim on every table:
   ```sql
   CREATE POLICY email_confirmed ON property_master_kl
     FOR ALL USING (
       auth.jwt()->>'email_confirmed' IS NOT NULL
     );
   ```
   This ensures that even if the app-layer check is bypassed, the database itself rejects queries from unconfirmed users.

---

## Finding 8: Signup Immediately Logs User In Without Email Verification

**Files:** `utils/auth.py` lines 298–340  
**Severity:** High

**Problem:**
```python
# auth.py:298-340
def sign_up_with_email_password(email: str, password: str):
    ...
    response = supabase.auth.sign_up(
        {"email": email, "password": password},
        {"data": {"role": "free"}}
    )
    ...
    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": _resolve_user_role(user, access_token=access_token),
        "email_confirmed": confirmed,  # <-- likely False
    }, None
```

After signup, the user receives full session tokens (`access_token`, `refresh_token`) **regardless of whether their email is confirmed**. The only thing preventing access is the app-layer check in `main.py` (Finding 7). This means:
- The user can call Supabase directly with their access token, bypassing the Streamlit app entirely
- If the app-layer check is missed on a new page, unconfirmed users have full access
- A user can sign up with a throwaway/disposable email and immediately have a valid JWT

**Fix instructions:**

1. Configure the Supabase project to **require email confirmation before issuing a session**. In the Supabase dashboard: Authentication → Settings → "Confirm email" → ON. This makes `supabase.auth.sign_up()` return `user` but **no session** until the email is confirmed.
2. Alternatively, after signup, **do not store the tokens in session state** — instead, show a success message telling the user to check their email, and redirect to the login page:
   ```python
   # After signup, if not confirmed:
   if not confirmed:
       st.session_state.auth_page = "login"
       st.session_state.auth_error = None
       st.sidebar.success(
           "Account created! Please check your email to confirm your account before logging in."
       )
       return None, None  # Don't return tokens
   ```
3. If you must keep the auto-login behavior, at minimum restrict the user's role to `"unconfirmed"` (which is checked in every RLS policy and app gate) instead of `"free"`.

---

## Finding 9: No Audit Logging for Any Auth Event

**Files:** `utils/auth.py` (entire file)  
**Severity:** High

**Problem:**
```python
# The entire auth.py file has zero logging statements.
# Failed logins, successful logins, registrations, password resets,
# role resolutions, and lockouts are all silent.

# auth.py:627 — the only print statement:
    print(auth_error)  # only prints to stdout, not a log file
```

There is no audit trail for:
- Successful and failed login attempts (with IP, email, timestamp)
- Account registrations
- Password reset requests and completions
- Role changes
- Token refresh failures
- Session restorations
- Logout events

If a breach or abuse occurs, there is zero forensic data to:
- Identify which accounts were compromised
- Determine the attacker's IP address
- Trace the timeline of the attack
- Produce evidence for law enforcement or compliance audits

**Fix instructions:**

1. Add structured logging using Python's `logging` module or a library like `structlog`:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

2. Add log statements at every auth entry point. Example pattern for login:
   ```python
   def login_with_email_password(email: str, password: str):
       ...
       # Before authentication
       logger.info("Login attempt", extra={"email": email, "ip": get_client_ip()})
       try:
           response = supabase.auth.sign_in_with_password(...)
       except Exception as exc:
           logger.warning("Login failed", extra={"email": email, "error": str(exc)})
           return None, str(exc)
       
       user, access_token, refresh_token, error = _normalize_response(response)
       if error:
           logger.warning("Login rejected", extra={"email": email, "error": error})
       else:
           logger.info("Login success", extra={"email": email, "user_id": user.get("id")})
       ...
   ```

3. Add log statements for:
   - `sign_up_with_email_password()` (success + failure)
   - `_try_refresh_session()` (success + failure)
   - `_try_restore_from_query_refresh_token()` (success + failure)
   - `logout()` (with user email)
   - `send_password_reset_email()` (with email)
   - `_detect_and_handle_recovery()` (success + failure)
   - `_resolve_user_role()` (role determined)
   - `_check_rate_limit()` (rate limit hit)

4. Remove the bare `print(auth_error)` on line 627 and replace with proper logging.

5. Configure log output in `main.py`:
   ```python
   logging.basicConfig(
       level=logging.INFO,
       format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
       handlers=[logging.StreamHandler()],  # or RotatingFileHandler for file output
   )
   ```

---

## Finding 10: Password Reset Endpoint Has No Rate Limiting

**Files:** `utils/auth.py` lines 450–456  
**Severity:** Medium

**Problem:**
```python
# auth.py:450-456
def send_password_reset_email(email: str) -> tuple[bool, str | None]:
    try:
        supabase = get_supabase_client()
        supabase.auth.reset_password_email(email)
    except Exception as exc:
        return False, str(exc)
    return True, None
```

There is no rate limiting on the password reset endpoint. An attacker can:
- Flood any user's email inbox with password reset emails (email bombing)
- Hit Supabase's email provider rate limit, causing legitimate resets to fail
- Enumerate valid email addresses by observing response timing or error messages
- Cause the organization to accrue unnecessary email sending costs

**Fix instructions:**

1. Add rate limiting to `send_password_reset_email()`:
   - Max 1 reset email per email address per 60 seconds
   - Max 3 reset emails per email address per 24 hours
   - Max 10 reset emails per IP address per 24 hours

2. Use a similar approach to the current `_check_rate_limit()` but with a shared store, or use a dedicated rate limiting service.

3. Example implementation:
   ```python
   _PASSWORD_RESET_ATTEMPTS: dict[str, list[float]] = {}
   _PASSWORD_RESET_MAX = 3
   _PASSWORD_RESET_WINDOW = 86400  # 24 hours
   _PASSWORD_RESET_COOLDOWN = 60   # 1 minute between resets

   def send_password_reset_email(email: str) -> tuple[bool, str | None]:
       now = _time.time()
       
       # Check cooldown
       attempts = _PASSWORD_RESET_ATTEMPTS.get(email, [])
       attempts = [t for t in attempts if now - t < _PASSWORD_RESET_WINDOW]
       if len(attempts) >= _PASSWORD_RESET_MAX:
           logger.warning("Password reset rate limited", extra={"email": email})
           return False, "Too many password reset requests. Please try again later."
       
       if attempts and (now - attempts[-1]) < _PASSWORD_RESET_COOLDOWN:
           return False, "Please wait before requesting another reset email."
       
       attempts.append(now)
       _PASSWORD_RESET_ATTEMPTS[email] = attempts
       
       try:
           supabase = get_supabase_client()
           supabase.auth.reset_password_email(email)
           logger.info("Password reset email sent", extra={"email": email})
           return True, None
       except Exception as exc:
           logger.error("Password reset email failed", extra={"email": email, "error": str(exc)})
           return False, str(exc)
   ```

4. Add a CAPTCHA check before the password reset form is submitted.

5. **Do not** reveal whether the email exists in the system. Always return the same message: "If an account with that email exists, a password reset link has been sent."

---

## Finding 12: Session Token Refresh Has a 10-Minute Blind Window

**Files:** `utils/auth.py` lines 70, 418–441, 444–447  
**Severity:** Medium

**Problem:**
```python
# auth.py:70
_TOKEN_REFRESH_INTERVAL = 3000  # 50 minutes (Supabase tokens expire in 60)

# auth.py:418-441
def _try_refresh_session() -> bool:
    refresh_token = st.session_state.get("auth_refresh_token")
    if not refresh_token:
        return False
    try:
        supabase = get_supabase_client()
        session = supabase.auth.refresh_session(refresh_token)
        ...
        if access:
            st.session_state.auth_access_token = access
            st.session_state.auth_refresh_token = refresh
            ...
            return True
    except Exception:
        pass
    return False

# auth.py:444-447
def ensure_valid_session() -> None:
    login_time = st.session_state.get("auth_login_time")
    if login_time and _time.time() - login_time > _TOKEN_REFRESH_INTERVAL:
        _try_refresh_session()
```

The token refresh interval is 3000 seconds (50 minutes), but Supabase access tokens expire at 3600 seconds (60 minutes). This creates a 10-minute window where a token could be expired but not yet refreshed. During this window, `load_property_data()` calls `supabase.postgrest.auth(token=access_token)` with a potentially expired token, which will fail silently or return a 401.

Additionally, `_try_refresh_session()` doesn't check if the token is actually expired before trying to refresh — it relies solely on the 50-minute clock, which can drift or be wrong if `auth_login_time` wasn't set correctly.

**Fix instructions:**

1. Reduce `_TOKEN_REFRESH_INTERVAL` to 3300 (55 minutes) to give a more comfortable 5-minute buffer.

2. Better yet, parse the JWT's `exp` claim to schedule the refresh precisely:
   ```python
   import jwt  # PyJWT
   
   def _get_token_expiry(access_token: str) -> float:
       try:
           decoded = jwt.decode(access_token, options={"verify_signature": False})
           return decoded.get("exp", 0)
       except Exception:
           return 0
   
   def ensure_valid_session() -> None:
       access_token = st.session_state.get("auth_access_token")
       if not access_token:
           return
       exp = _get_token_expiry(access_token)
       if not exp:
           return
       # Refresh if less than 5 minutes until expiry
       if exp - _time.time() < 300:
           _try_refresh_session()
   ```

3. In `load_property_data()` in `utils/data_loader.py`, handle the 401 case by triggering a refresh and retrying:
   ```python
   def load_property_data(access_token: str | None = None, role: str | None = None) -> pd.DataFrame:
       supabase = get_supabase_client()
       supabase.postgrest.auth(token=access_token)
       try:
           response = supabase.schema("main").table("property_master_kl").select("*").execute()
       except Exception as exc:
           # If 401, try to refresh and retry
           if "401" in str(exc):
               from .auth import _try_refresh_session
               if _try_refresh_session():
                   supabase = get_supabase_client()
                   supabase.postgrest.auth(token=st.session_state.get("auth_access_token"))
                   response = supabase.schema("main").table("property_master_kl").select("*").execute()
               else:
                   raise RuntimeError("Session expired and could not be refreshed. Please log in again.")
           else:
               raise
   ```

---

## Finding 13: Service Role Key Loaded into Application Process

**Files:** `utils/supabase_client.py` lines 36–44; `utils/auth.py` lines 248–268  
**Severity:** High

**Problem:**
```python
# supabase_client.py:36-44
def get_supabase_service_client() -> Client:
    """Create a Supabase client using the service_role key (bypasses RLS)."""
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in the environment."
        )
    return create_client(supabase_url, service_key)

# auth.py:248-268
def create_user_profile(user_id: str, email: str, role: str = "free"):
    """Uses the service_role key to bypass RLS (SUPABASE_KEY has read-only access)."""
    try:
        supabase = get_supabase_service_client()
        response = supabase.schema("main").table("profiles").insert(...).execute()
    except Exception as exc:
        return None, str(exc)
```

The `SUPABASE_SERVICE_KEY` bypasses all Row-Level Security policies — it is a super-admin credential. It is loaded into the application process and used at runtime. If an attacker gains:
- Remote Code Execution (RCE) on the server
- Read access to environment variables (via `/proc/self/environ`, debug endpoints, etc.)
- Access to a crash dump or memory dump
- Access to the server's file system (via path traversal, SSRF, etc.)

...they obtain a key that gives **unrestricted read/write access to every table in the entire Supabase project**, including the ability to modify any user's role to "subscribed".

**Fix instructions:**

1. **Do not use the service_role key in the application process at all.** It should only be used in:
   - Supabase Edge Functions (serverless, isolated)
   - Database migrations
   - Admin CLI tools
   - CI/CD pipelines

2. Replace `create_user_profile()` with a **Supabase Database Function** that uses `SECURITY DEFINER`:
   ```sql
   CREATE OR REPLACE FUNCTION main.create_user_profile(
       p_user_id UUID,
       p_email TEXT,
       p_role TEXT DEFAULT 'free'
   ) RETURNS void
   LANGUAGE plpgsql
   SECURITY DEFINER
   SET search_path = main
   AS $$
   BEGIN
       INSERT INTO main.profiles (user_id, email, role)
       VALUES (p_user_id, p_email, p_role)
       ON CONFLICT (user_id) DO NOTHING;
   END;
   $$;
   ```
   Then call it via `supabase.rpc("create_user_profile", ...)` from the anon-key client — the function runs with the privileges of the function owner, bypassing RLS only for this specific operation.

3. If you cannot use Database Functions, at minimum:
   - Restrict the service key's network access using Supabase's Network Restrictions (limit to your deployment's IP range).
   - Rotate the service key regularly.
   - Never log the service key.
   - Audit all uses of the service key and keep them to an absolute minimum.

4. Remove the `SUPABASE_SERVICE_KEY` environment variable from the deployment and the `.env` file.

---

## Finding 15: No HTTPS Enforcement or Security Headers

**Files:** Not in application code — implied by lack of configuration  
**Severity:** High

**Problem:**
```python
# main.py — no TLS/HTTPS configuration
# No reference to HSTS, CSP, or other security headers anywhere in the codebase
```

There is no evidence of:
- HTTPS enforcement (the Streamlit server may be accessible over plain HTTP)
- `Strict-Transport-Security` header
- `Content-Security-Policy` header
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`

Since Findings 1 and 2 place sensitive tokens in URL query parameters, HTTP access means those tokens are transmitted in **plaintext** over the network, making them trivially interceptable via:
- Man-in-the-middle attacks on public Wi-Fi
- Rogue access points
- Compromised network infrastructure
- Packet sniffing on shared networks

**Fix instructions:**

1. If using a reverse proxy (nginx, Caddy, Traefik, Cloudflare):
   - **Enforce HTTPS**: redirect all HTTP traffic to HTTPS.
   - **Set HSTS**: `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
   - **Set CSP**: `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.plot.ly; ...`
   - **Set other headers**:
     ```
     X-Content-Type-Options: nosniff
     X-Frame-Options: DENY
     Referrer-Policy: no-referrer
     ```

2. If Streamlit is exposed directly, configure `config.toml`:
   ```toml
   [server]
   enableCORS = true
   enableXsrfProtection = true
   cookieSecret = "<random-64-char-string>"
   sslCertFile = "/path/to/cert.pem"
   sslKeyFile = "/path/to/key.pem"
   ```

3. Set `Referrer-Policy: no-referrer` to prevent token leakage via the HTTP Referer header (critical given Findings 1 and 2).

4. Add a security middleware in the reverse proxy or at the Streamlit app level that sets these headers on every response.

---

## Finding 16: Password Update Does Not Re-Authenticate User

**Files:** `utils/auth.py` lines 459–469; `render_auth_sidebar` lines 535–555  
**Severity:** High

**Problem:**
```python
# auth.py:459-469
def update_password(new_password: str) -> tuple[bool, str | None]:
    ensure_valid_session()
    try:
        supabase = get_supabase_client(
            access_token=st.session_state.get("auth_access_token"),
            refresh_token=st.session_state.get("auth_refresh_token"),
        )
        supabase.auth.update_user({"password": new_password})
    except Exception as exc:
        return False, str(exc)
    return True, None

# render_auth_sidebar lines 535-555:
    with st.sidebar.form("reset_password_form"):
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Reset Password")
        if submitted:
            if not new_password:
                st.sidebar.error("Password is required.")
            elif new_password != confirm_password:
                st.sidebar.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.sidebar.error("Password must be at least 6 characters.")
            else:
                _, error = update_password(new_password)
```

The password update flow:
- Does **not** require the user's **current password**
- Does **not** require re-authentication
- Only validates that the new password is at least 6 characters

If an attacker gains temporary access to an unattended, authenticated session (e.g., a user walks away from their computer, or an XSS vulnerability exists), they can **immediately change the password** and permanently lock the legitimate user out.

**Fix instructions:**

1. Add a "Current Password" field to the reset password form:
   ```python
   with st.sidebar.form("reset_password_form"):
       current_password = st.text_input("Current Password", type="password")
       new_password = st.text_input("New Password", type="password")
       confirm_password = st.text_input("Confirm New Password", type="password")
       submitted = st.form_submit_button("Reset Password")
       if submitted:
           if not current_password:
               st.sidebar.error("Current password is required.")
           elif not new_password:
               st.sidebar.error("New password is required.")
           elif new_password != confirm_password:
               st.sidebar.error("Passwords do not match.")
           elif new_password == current_password:
               st.sidebar.error("New password must be different from current password.")
           else:
               _, error = update_password(current_password, new_password)
   ```

2. Update `update_password()` to re-authenticate the user with their current password before changing it:
   ```python
   def update_password(current_password: str, new_password: str) -> tuple[bool, str | None]:
       ensure_valid_session()
       email = st.session_state.get("auth_user", {}).get("email")
       if not email:
           return False, "No authenticated user found."
       
       try:
           # Re-authenticate with current password first
           supabase = get_supabase_client()
           supabase.auth.sign_in_with_password(
               {"email": email, "password": current_password}
           )
       except Exception as exc:
           return False, "Current password is incorrect."
       
       try:
           supabase = get_supabase_client(
               access_token=st.session_state.get("auth_access_token"),
               refresh_token=st.session_state.get("auth_refresh_token"),
           )
           supabase.auth.update_user({"password": new_password})
           logger.info("Password changed successfully", extra={"email": email})
           return True, None
       except Exception as exc:
           logger.error("Password change failed", extra={"email": email, "error": str(exc)})
           return False, str(exc)
   ```

3. Strengthen password validation (minimum 12 chars, complexity requirements).

4. After a password change, send a confirmation email to the user's registered email address notifying them of the change.

5. Offer the option to "Log out of all other devices" after a password change.
