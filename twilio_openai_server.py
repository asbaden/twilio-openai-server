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
VOICE = "echo"  # Options: alloy, ash, ballad, coral, echo, sage, shimmer, verse
SYSTEM_MESSAGE = "You are Claude, a helpful AI assistant speaking with Gus. Keep your responses concise and conversational. You're speaking on a phone call."
LOG_EVENT_TYPES = ["session.updated", "response.text.delta", "turn.start", "turn.end", "error"]

# Counter for audio packets
audio_packets_from_twilio = 0
audio_packets_to_twilio = 0

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
                        # Make the call using Twilio
                        response = requests.post(
                            f'https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json',
                            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                            data={
                                'To': call['phone_number'],
                                'From': TWILIO_PHONE_NUMBER,
                                'Url': f'https://{os.getenv("RENDER_URL", "twilio-openai-server.onrender.com")}/voice'
                            }
                        )
                        
                        if response.status_code == 201:
                            # Update call status to completed
                            supabase.table('scheduled_calls').update({
                                'status': 'completed',
                                'call_sid': response.json()['sid']
                            }).eq('id', call['id']).execute()
                            logger.info(f"Successfully initiated call {call['id']}")
                        else:
                            # Update call status to failed
                            supabase.table('scheduled_calls').update({
                                'status': 'failed',
                                'error_message': f"Twilio API error: {response.text}"
                            }).eq('id', call['id']).execute()
                            logger.error(f"Failed to initiate call {call['id']}: {response.text}")
                            
                    except Exception as e:
                        # Update call status to failed
                        supabase.table('scheduled_calls').update({
                            'status': 'failed',
                            'error_message': str(e)
                        }).eq('id', call['id']).execute()
                        logger.error(f"Error processing call {call['id']}: {str(e)}")
            
            # Sleep for 1 minute before checking again
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in check_scheduled_calls: {str(e)}")
            time.sleep(60)  # Sleep for 1 minute before retrying

# Start the background task
scheduler_thread = threading.Thread(target=check_scheduled_calls, daemon=True)
scheduler_thread.start()

@app.route('/schedule_call', methods=['POST'])
def schedule_call():
    """Handle call scheduling requests"""
    try:
        data = request.get_json()
        logger.info(f"Received scheduling request: {data}")
        
        # Validate required fields
        if not data or 'phone_number' not in data or 'scheduled_time' not in data:
            return Response(
                json.dumps({"error": "Missing required fields: phone_number and scheduled_time"}),
                status=400,
                mimetype='application/json'
            )
        
        # Insert into Supabase
        result = supabase.table('scheduled_calls').insert({
            'phone_number': data['phone_number'],
            'scheduled_time': data['scheduled_time'],
            'status': 'pending',
            'metadata': data.get('metadata', {})
        }).execute()
        
        logger.info(f"Scheduled call created: {result}")
        
        return Response(
            json.dumps({"message": "Call scheduled successfully", "data": result.data[0]}),
            status=200,
            mimetype='application/json'
        )
        
    except Exception as e:
        logger.error(f"Error scheduling call: {str(e)}")
        return Response(
            json.dumps({"error": str(e)}),
            status=500,
            mimetype='application/json'
        )

# Route to handle incoming calls
@app.route('/voice', methods=['POST'])
def voice():
    """Handle incoming voice calls"""
    # Get call SID
    call_sid = request.values.get('CallSid')
    logger.info(f"Incoming call: {call_sid}")
    logger.debug(f"Request values: {request.values}")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Add a welcome message
    response.say("Hey Gus, what would you like to get done today?", voice="Polly.Amy-Neural")
    
    # Add a pause after the welcome message
    response.pause(length=2)
    
    # Connect to the WebSocket for media streaming
    start = Start()
    # Use the full URL with https:// prefix
    stream_url = f'wss://{request.host}/media-stream'
    logger.info(f"Setting up WebSocket stream with URL: {stream_url}")
    start.stream(url=stream_url)
    response.append(start)
    
    # Add a longer pause to ensure the WebSocket connection is established
    response.pause(length=3)
    
    # Log the full TwiML response
    twiml_response = str(response)
    logger.info(f"Generated TwiML response: {twiml_response}")
    
    return twiml_response

# WebSocket handler for media streams
@sock.route('/media-stream')
def handle_media_stream(ws):
    """Handle WebSocket connection for media streaming"""
    try:
        logger.info("Client connected to WebSocket")
        
        # Send initial connection confirmation
        ws.send(json.dumps({"event": "connected"}))
        logger.info("Sent initial connection confirmation")
        
        # Connect to OpenAI Realtime API
        logger.info("Connecting to OpenAI Realtime API...")
        logger.debug(f"Using OpenAI API Key: sk-tX{OPENAI_API_KEY[:4]}...")
        
        # Create WebSocket connection to OpenAI
        openai_ws = websocket.WebSocketApp(
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
            header={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            },
            on_message=lambda ws, msg: handle_openai_message(ws, msg, twilio_ws=ws),
            on_error=lambda ws, err: logger.error(f"OpenAI WebSocket error: {err}"),
            on_close=lambda ws: logger.info("OpenAI WebSocket closed")
        )
        
        # Start OpenAI WebSocket connection in a separate thread
        openai_thread = threading.Thread(target=openai_ws.run_forever)
        openai_thread.daemon = True
        openai_thread.start()
        
        logger.info("Connected to OpenAI Realtime API successfully")
        
        # Send session update to OpenAI
        logger.info("Sending session update to OpenAI")
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": VOICE,
                "instructions": SYSTEM_MESSAGE,
                "modalities": ["text", "audio"],
                "temperature": 0.8
            }
        }
        logger.debug(f"Session update data: {session_update}")
        openai_ws.send(json.dumps(session_update))
        logger.info("Session update sent successfully")
        
        # Track stream SID
        stream_sid = None
        
        # Start receiving messages from Twilio
        while True:
            try:
                message = ws.receive()
                data = json.loads(message)
                
                if data.get("event") == "start":
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"Incoming stream has started: {stream_sid}")
                    
                elif data.get("event") == "media" and stream_sid:
                    # Forward audio to OpenAI
                    openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": data["media"]["payload"]
                    }))
                    logger.debug("Successfully sent audio to OpenAI")
                    
            except Exception as e:
                logger.error(f"Error processing Twilio message: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Error in handle_media_stream: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        try:
            openai_ws.close()
            ws.close()
            logger.info("WebSocket connections closed")
        except:
            pass

def handle_openai_message(ws, message, twilio_ws):
    """Handle messages received from OpenAI WebSocket"""
    try:
        response = json.loads(message)
        
        if response.get("type") in LOG_EVENT_TYPES:
            logger.info(f"Received event from OpenAI: {response['type']}")
            logger.debug(f"Event data: {response}")
            
        if response.get("type") == "output_audio_buffer.append":
            # Forward audio to Twilio
            twilio_ws.send(json.dumps({
                "event": "media",
                "media": {
                    "payload": response["audio"]
                }
            }))
            logger.debug("Successfully sent audio to Twilio")
            
        elif response.get("type") == "response.text.delta":
            # Log text responses
            logger.info(f"AI response: {response.get('text', '')}")
            
    except Exception as e:
        logger.error(f"Error handling OpenAI message: {str(e)}")

# Main function
def main():
    """Main function"""
    logger.info("Starting Twilio-OpenAI server")
    logger.info(f"Using OpenAI voice: {VOICE}")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)

if __name__ == '__main__':
    main() 