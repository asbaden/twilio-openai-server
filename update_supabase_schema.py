import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

def update_schema():
    try:
        # Create the calls table if it doesn't exist
        response = supabase.table('calls').select('*').limit(1).execute()
        
        # Define the new schema
        schema = {
            'id': 'uuid',
            'created_at': 'timestamp with time zone',
            'phone_number': 'text',
            'status': 'text',
            'scheduled_time': 'timestamp with time zone',
            'completed_at': 'timestamp with time zone',
            'error_message': 'text',
            'call_sid': 'text',
            'conversation_id': 'text',
            'transcript': 'text',
            'metadata': 'jsonb'
        }
        
        # Update the table schema
        for column, data_type in schema.items():
            try:
                # Check if column exists
                supabase.table('calls').select(column).limit(1).execute()
            except Exception:
                # Column doesn't exist, add it
                print(f"Adding column: {column}")
                supabase.table('calls').alter_table({
                    'add_column': {
                        'name': column,
                        'type': data_type
                    }
                })
        
        print("Schema update completed successfully!")
        
    except Exception as e:
        print(f"Error updating schema: {str(e)}")

if __name__ == "__main__":
    update_schema() 