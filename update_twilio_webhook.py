import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from parent directory
load_dotenv('../.env')

# Get Twilio credentials from environment variables
account_sid = os.getenv('EXPO_PUBLIC_TWILIO_ACCOUNT_SID')
auth_token = os.getenv('EXPO_PUBLIC_TWILIO_AUTH_TOKEN')
phone_number = os.getenv('EXPO_PUBLIC_TWILIO_PHONE_NUMBER')

# Check if ngrok URL was provided as command line argument
if len(sys.argv) < 2:
    print("Please provide your ngrok URL as a command line argument")
    print("Example: python update_twilio_webhook.py https://your-ngrok-url.ngrok.io")
    sys.exit(1)

# Get ngrok URL from command line argument
ngrok_url = sys.argv[1]

# Create Twilio client
client = Client(account_sid, auth_token)

# Update phone number with new voice URL
try:
    phone_number_obj = client.incoming_phone_numbers.list(phone_number=phone_number)[0]
    
    updated_number = client.incoming_phone_numbers(phone_number_obj.sid).update(
        voice_url=f"{ngrok_url}/voice",
        voice_method="POST"
    )
    
    print(f"Successfully updated {phone_number} to use webhook URL: {ngrok_url}/voice")
    print("You can now call your Twilio number to test the voice assistant!")
except Exception as e:
    print(f"Error updating phone number: {e}") 