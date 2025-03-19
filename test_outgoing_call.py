import os
from twilio.rest import Client
from dotenv import load_dotenv
import sys

# Load environment variables from the current directory
load_dotenv()

# Get Twilio credentials from environment variables
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')

print(f"Account SID: {account_sid[:5]}...{account_sid[-5:] if account_sid else None}")
print(f"Auth Token: {auth_token[:5]}...{auth_token[-5:] if auth_token else None}")
print(f"Twilio Phone Number: {twilio_phone_number}")

# Create Twilio client
client = Client(account_sid, auth_token)

# Check command line arguments
if len(sys.argv) < 2:
    print("Please provide your phone number as a command line argument")
    print("Example: python test_outgoing_call.py +1234567890")
    sys.exit(1)

# Get the destination phone number from the command line
to_phone_number = sys.argv[1]

# Get your Render URL - replace this with your actual Render URL
render_url = "https://twilio-openai-server.onrender.com/voice"

# Make the call
try:
    call = client.calls.create(
        to=to_phone_number,
        from_=twilio_phone_number,
        url=render_url,
        method="POST"
    )
    
    print(f"Call initiated with SID: {call.sid}")
    print(f"Calling {to_phone_number} from {twilio_phone_number}")
    print(f"Using webhook URL: {render_url}")
    print("You should receive a call shortly!")
except Exception as e:
    print(f"Error making call: {e}") 