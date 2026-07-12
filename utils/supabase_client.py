import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


def get_supabase_client(
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> Client:
    """Create a shared Supabase client using environment variables.

    If an authenticated user session is available, attach their JWT so
    Supabase can evaluate RLS policies for the authenticated role.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in the environment."
        )

    client = create_client(supabase_url, supabase_key)
    if access_token:
        client.auth.set_session(access_token, refresh_token)
    return client