import os
import json
import base64
import asyncio
import websockets
import logging
from flask import Flask, request, Response
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Connect, Start
from dotenv import load_dotenv
import threading
import traceback
from supabase import create_client, Client
from datetime import datetime, timezone
import requests
import time
import websocket

# Load environment variables
load_dotenv()

# Configure logging - set to DEBUG for more detailed logs
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
sock = Sock(app)

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_ANON_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Constants
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
RENDER_URL = os.getenv('RENDER_URL', 'twilio-openai-server.onrender.com')
VOICE = "echo"  # Options: alloy, ash, ballad, coral, echo, sage, shimmer, verse
SYSTEM_MESSAGE = "You are Claude, a helpful AI assistant speaking with Gus. Keep your responses concise and conversational. You're speaking on a phone call."
LOG_EVENT_TYPES = ["session.updated", "response.text.delta", "turn.start", "turn.end", "error"]

# Counter for audio packets
audio_packets_from_twilio = 0
audio_packets_to_twilio = 0

def validate_phone_number(phone_number):
    """Validate phone number format and add + prefix if needed"""
    # Remove any spaces or special characters
    cleaned = ''.join(filter(str.isdigit, phone_number))
    
    # Add country code if not present
    if len(cleaned) == 10:  # US number without country code
        return f"+1{cleaned}"
    elif len(cleaned) == 11 and cleaned.startswith('1'):  # US number with country code
        return f"+{cleaned}"
    elif cleaned.startswith('1'):  # Number already has country code
        return f"+{cleaned}"
    else:
        raise ValueError("Invalid phone number format. Please provide a valid US phone number.")

def validate_scheduled_time(scheduled_time):
    """Validate scheduled time format and ensure it's in the future"""
    try:
        # Parse the scheduled time
        scheduled = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        
        # Ensure it's in the future
        if scheduled <= datetime.now(timezone.utc):
            raise ValueError("Scheduled time must be in the future")
            
        return scheduled.isoformat()
    except Exception as e:
        raise ValueError(f"Invalid scheduled time format. Please use ISO format (YYYY-MM-DDTHH:MM:SSZ). Error: {str(e)}")

@app.route('/schedule_call', methods=['POST'])
def schedule_call():
    """Handle call scheduling requests"""
    try:
        data = request.get_json()
        logger.info(f"Received scheduling request: {data}")
        
        # Validate required fields
        if not data:
            raise ValueError("Request body is required")
            
        if 'phone_number' not in data:
            raise ValueError("phone_number is required")
            
        if 'scheduled_time' not in data:
            raise ValueError("scheduled_time is required")
        
        # Validate and format phone number
        phone_number = validate_phone_number(data['phone_number'])
        
        # Validate and format scheduled time
        scheduled_time = validate_scheduled_time(data['scheduled_time'])
        
        # Construct the voice URL and callback URL
        voice_url = f"https://{RENDER_URL}/voice"
        callback_url = f"https://{RENDER_URL}/call_status"
        logger.info(f"Voice URL for scheduled call: {voice_url}")
        logger.info(f"Callback URL for scheduled call: {callback_url}")
        
        # Insert into Supabase
        result = supabase.table('scheduled_calls').insert({
            'phone_number': phone_number,
            'scheduled_time': scheduled_time,
            'status': 'pending',
            'metadata': data.get('metadata', {}),
            'voice_url': voice_url,
            'callback_url': callback_url
        }).execute()
        
        logger.info(f"Scheduled call created: {result.data[0]}")
        
        return Response(
            json.dumps({
                "message": "Call scheduled successfully",
                "data": {
                    "id": result.data[0]['id'],
                    "phone_number": phone_number,
                    "scheduled_time": scheduled_time,
                    "status": "pending",
                    "voice_url": voice_url,
                    "callback_url": callback_url
                }
            }),
            status=200,
            mimetype='application/json'
        )
        
    except ValueError as e:
        logger.warning(f"Validation error in schedule_call: {str(e)}")
        return Response(
            json.dumps({"error": str(e)}),
            status=400,
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Error scheduling call: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(
            json.dumps({"error": "Internal server error. Please try again later."}),
            status=500,
            mimetype='application/json'
        )

def check_scheduled_calls():
    """Background task to check for and execute scheduled calls"""
    while True:
        try:
            # Get current time in UTC
            now = datetime.now(timezone.utc)
            
            # Query for pending calls that are due
            result = supabase.table('scheduled_calls').select("*").eq('status', 'pending').execute()
            
            for call in result.data:
                scheduled_time = datetime.fromisoformat(call['scheduled_time'].replace('Z', '+00:00'))
                
                # If the scheduled time has passed
                if scheduled_time <= now:
                    try:
                        # Get the voice URL and callback URL from the call record
                        voice_url = call.get('voice_url') or f"https://{RENDER_URL}/voice"
                        callback_url = call.get('callback_url') or f"https://{RENDER_URL}/call_status"
                        
                        # Make the call using Twilio
                        response = requests.post(
                            f'https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json',
                            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                            data={
                                'To': call['phone_number'],
                                'From': TWILIO_PHONE_NUMBER,
                                'Url': voice_url,
                                'StatusCallback': callback_url,
                                'StatusCallbackEvent': ['initiated', 'ringing', 'answered', 'completed'],
                                'StatusCallbackMethod': 'POST'
                            }
                        )
                        
                        response_data = response.json()
                        
                        if response.status_code == 201:
                            # Update call status to in_progress
                            supabase.table('scheduled_calls').update({
                                'status': 'in_progress',
                                'call_sid': response_data['sid'],
                                'started_at': datetime.now(timezone.utc).isoformat(),
                                'twilio_response': response_data
                            }).eq('id', call['id']).execute()
                            logger.info(f"Successfully initiated call {call['id']} with SID {response_data['sid']}")
                        else:
                            # Update call status to failed
                            supabase.table('scheduled_calls').update({
                                'status': 'failed',
                                'error_message': f"Twilio API error: {response.text}",
                                'twilio_response': response_data
                            }).eq('id', call['id']).execute()
                            logger.error(f"Failed to initiate call {call['id']}: {response.text}")
                            
                    except Exception as e:
                        logger.error(f"Error processing call {call['id']}: {str(e)}")
                        logger.error(traceback.format_exc())
                        # Update call status to failed
                        supabase.table('scheduled_calls').update({
                            'status': 'failed',
                            'error_message': str(e)
                        }).eq('id', call['id']).execute()
            
            # Sleep for 1 minute before checking again
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in check_scheduled_calls: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(60)  # Sleep for 1 minute before retrying

@app.route('/call_status', methods=['POST'])
def call_status():
    """Handle Twilio call status callbacks"""
    try:
        # Get call details from the request
        call_sid = request.values.get('CallSid')
        call_status = request.values.get('CallStatus')
        
        logger.info(f"Received status update for call {call_sid}: {call_status}")
        
        # Find the call in our database
        result = supabase.table('scheduled_calls').select("*").eq('call_sid', call_sid).execute()
        
        if result.data:
            call = result.data[0]
            
            # Update the call status
            update_data = {
                'twilio_status': call_status,
                'last_status_update': datetime.now(timezone.utc).isoformat()
            }
            
            # If the call is complete or failed, update the status
            if call_status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
                update_data['status'] = 'completed'
                update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
            
            supabase.table('scheduled_calls').update(update_data).eq('id', call['id']).execute()
            logger.info(f"Updated status for call {call['id']}")
        
        return Response(status=200)
    
    except Exception as e:
        logger.error(f"Error handling call status: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(status=500)

def create_openai_session():
    """Create a new OpenAI Realtime session"""
    response = requests.post(
        'https://api.openai.com/v1/realtime/sessions',
        headers={
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'gpt-4o-realtime-preview-2024-12-17',
            'modalities': ['audio', 'text'],
            'instructions': SYSTEM_MESSAGE,
            'voice': VOICE,
            'input_audio_format': 'pcm16',
            'output_audio_format': 'pcm16',
            'input_audio_transcription': {
                'model': 'whisper-1'
            },
            'turn_detection': {
                'type': 'server_vad',
                'threshold': 0.5,
                'prefix_padding_ms': 300,
                'silence_duration_ms': 500,
                'create_response': True
            }
        }
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to create OpenAI session: {response.text}")
        
    session = response.json()
    logger.info(f"Created OpenAI session: {session['id']}")
    return session

def handle_media_stream(ws):
    """Handle media stream from Twilio"""
    try:
        # Create OpenAI session
        session = create_openai_session()
        client_secret = session['client_secret']['value']
        
        # Connect to OpenAI WebSocket
        openai_ws = websocket.WebSocketApp(
            'wss://api.openai.com/v1/audio-chat/realtime',
            header={
                'Authorization': f'Bearer {client_secret}',
                'Content-Type': 'application/json'
            },
            on_message=lambda ws, msg: handle_openai_message(ws, msg, ws),
            on_error=lambda ws, error: logger.error(f"OpenAI WebSocket error: {error}"),
            on_close=lambda ws, code, reason: logger.info(f"OpenAI WebSocket closed: {code} - {reason}")
        )
        
        # Start OpenAI WebSocket connection
        openai_ws_thread = threading.Thread(target=openai_ws.run_forever)
        openai_ws_thread.daemon = True
        openai_ws_thread.start()
        
        # Wait for OpenAI connection
        timeout = time.time() + 10  # 10 second timeout
        while not openai_ws.sock or not openai_ws.sock.connected:
            if time.time() > timeout:
                raise Exception("Timeout waiting for OpenAI connection")
            time.sleep(0.1)
            
        logger.info("OpenAI WebSocket connected")
        
        # Send initial session configuration
        openai_ws.send(json.dumps({
            'type': 'session.update',
            'session': {
                'modalities': ['audio', 'text'],
                'instructions': SYSTEM_MESSAGE,
                'voice': VOICE,
                'input_audio_format': 'pcm16',
                'output_audio_format': 'pcm16'
            }
        }))
        
        # Handle Twilio audio stream
        while True:
            message = ws.receive()
            if message is None:
                break
                
            # Parse Twilio message
            twilio_msg = json.loads(message)
            if twilio_msg['event'] == 'media':
                # Decode audio data
                audio_data = base64.b64decode(twilio_msg['media']['payload'])
                
                # Send audio to OpenAI
                openai_ws.send(json.dumps({
                    'type': 'input_audio_buffer.append',
                    'audio': base64.b64encode(audio_data).decode('utf-8')
                }))
                
            elif twilio_msg['event'] == 'stop':
                break
                
    except Exception as e:
        logger.error(f"Error in handle_media_stream: {str(e)}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if 'openai_ws' in locals():
            openai_ws.close()

def handle_openai_message(ws, message, twilio_ws):
    """Handle messages from OpenAI WebSocket"""
    try:
        msg = json.loads(message)
        msg_type = msg.get('type')
        
        if msg_type == 'response.audio.delta':
            # Send audio to Twilio
            audio_data = base64.b64decode(msg['delta'])
            twilio_ws.send(json.dumps({
                'event': 'media',
                'streamSid': 'STREAM_SID',
                'media': {
                    'payload': base64.b64encode(audio_data).decode('utf-8')
                }
            }))
            
        elif msg_type == 'error':
            logger.error(f"OpenAI error: {msg['error']}")
            
    except Exception as e:
        logger.error(f"Error handling OpenAI message: {str(e)}")
        logger.error(traceback.format_exc())

@app.route('/voice', methods=['POST'])
def voice():
    """Handle incoming voice calls"""
    response = VoiceResponse()
    start = Start()
    start.stream(url=f'wss://{request.host}/media-stream')
    response.append(start)
    
    connect = Connect()
    connect.stream(url=f'wss://{request.host}/media-stream')
    response.append(connect)
    
    return str(response)

@sock.route('/media-stream')
def media_stream(ws):
    """Handle WebSocket connection for media streaming"""
    try:
        handle_media_stream(ws)
    except Exception as e:
        logger.error(f"Error in media_stream: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(status=500)

# Main function
def main():
    """Main function"""
    logger.info("Starting Twilio-OpenAI server")
    logger.info(f"Using OpenAI voice: {VOICE}")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)

if __name__ == '__main__':
    main() 