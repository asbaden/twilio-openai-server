import os
from dotenv import load_dotenv
from supabase import create_client, Client
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

supabase: Client = create_client(supabase_url, supabase_key)

def run_migration():
    """Run the SQL migration to create the scheduled_calls table."""
    try:
        # Read the SQL file
        with open('migrations/001_create_scheduled_calls.sql', 'r') as f:
            sql = f.read()
        
        # Execute the SQL
        result = supabase.rpc('exec_sql', {'sql': sql}).execute()
        
        logger.info("Migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running migration: {e}")
        return False

if __name__ == "__main__":
    run_migration() 