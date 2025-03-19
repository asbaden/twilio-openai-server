import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

def run_migration():
    """Run the SQL migration to create the scheduled_calls table"""
    try:
        # Read the migration file
        migration_path = os.path.join(os.path.dirname(__file__), 'migrations', '001_create_scheduled_calls.sql')
        with open(migration_path, 'r') as f:
            sql = f.read()
        
        # Execute the migration
        logger.info("Running migration to create scheduled_calls table...")
        result = supabase.rpc('exec_sql', {'sql': sql}).execute()
        
        if hasattr(result, 'error') and result.error:
            logger.error(f"Migration failed: {result.error}")
            return False
        
        logger.info("Migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error running migration: {str(e)}")
        return False

if __name__ == '__main__':
    run_migration() 