"""
Singleton Supabase client.
Import `supabase` from this module anywhere in the backend.
"""
import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
