#!/usr/bin/env python3

import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('../.env')

# Get Twilio credentials from environment variables
account_sid = os.getenv('EXPO_PUBLIC_TWILIO_ACCOUNT_SID')
auth_token = os.getenv('EXPO_PUBLIC_TWILIO_AUTH_TOKEN')
twilio_phone_number = os.getenv('EXPO_PUBLIC_TWILIO_PHONE_NUMBER')

# Print environment variables for debugging (without revealing full credentials)
print(f"Account SID: {account_sid[:5]}...{account_sid[-5:] if account_sid else None}")
print(f"Auth Token: {auth_token[:5]}...{auth_token[-5:] if auth_token else None}")
print(f"Twilio Phone Number: {twilio_phone_number}")

# New ngrok URL
ngrok_url = "https://0300-2603-8000-d101-8c1f-6052-4e2a-fa21-729c.ngrok-free.app"

# Initialize Twilio client
if account_sid and auth_token:
    client = Client(account_sid, auth_token)
    
    try:
        # Get the phone number
        phone_numbers = client.incoming_phone_numbers.list(phone_number=twilio_phone_number)
        
        if phone_numbers:
            phone_number = phone_numbers[0]
            
            # Update the voice URL
            phone_number.update(voice_url=f"{ngrok_url}/voice")
            
            print(f"Successfully updated voice URL for {twilio_phone_number} to {ngrok_url}/voice")
        else:
            print(f"No phone number found matching {twilio_phone_number}")
    except Exception as e:
        print(f"Error updating Twilio phone number: {e}")
else:
    print("Missing Twilio credentials. Please check your .env file.") 