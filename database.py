import os
from supabase import create_client, Client
from dotenv import load_dotenv

# This loads the keys from your .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials. Check your .env file!")

# This creates the connection we will use in our main app
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)