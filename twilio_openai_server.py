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

# Load environment variables
load_dotenv()

# Configure logging - set to DEBUG for more detailed logs
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
sock = Sock(app)

# Constants
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
VOICE = "echo"  # Options: alloy, ash, ballad, coral, echo, sage, shimmer, verse
SYSTEM_MESSAGE = "You are Claude, a helpful AI assistant speaking with Gus. Keep your responses concise and conversational. You're speaking on a phone call."
LOG_EVENT_TYPES = ["session.updated", "response.text.delta", "turn.start", "turn.end", "error"]

# Counter for audio packets
audio_packets_from_twilio = 0
audio_packets_to_twilio = 0

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
async def handle_media_stream(ws):
    """Handle WebSocket connection for media streaming"""
    try:
        # Send initial connection confirmation
        await ws.send(json.dumps({"event": "connected"}))
        logger.info("Sent initial connection confirmation")
        
        # Connect to OpenAI Realtime API
        logger.info("Connecting to OpenAI Realtime API...")
        logger.debug(f"Using OpenAI API Key: sk-tX{OPENAI_API_KEY[:4]}...")
        
        async with websockets.connect(
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
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
            await openai_ws.send(json.dumps(session_update))
            logger.info("Session update sent successfully")
            
            # Start WebSocket receiver
            logger.info("Starting WebSocket receiver")
            receiver_task = asyncio.create_task(ws_receiver(openai_ws, ws))
            
            # Start audio streaming between Twilio and OpenAI
            logger.info("Starting audio streaming between Twilio and OpenAI")
            try:
                logger.debug("Starting to receive from Twilio")
                async for message in ws:
                    try:
                        data = json.loads(message)
                        if data.get("event") == "media":
                            # Forward audio to OpenAI
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data["media"]["payload"]
                            }))
                            logger.debug("Successfully sent audio to OpenAI")
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
                        continue
            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket connection closed normally")
            except Exception as e:
                logger.error(f"Error in WebSocket receive process: {str(e)}")
                logger.error(traceback.format_exc())
            finally:
                # Cancel receiver task
                receiver_task.cancel()
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass
                
                # Close connections
                try:
                    await ws.close()
                    logger.info("WebSocket connection closed")
                except Exception as e:
                    logger.error(f"Error closing WebSocket: {str(e)}")
                    logger.error(traceback.format_exc())
                
    except Exception as e:
        logger.error(f"Error in handle_media_stream: {str(e)}")
        logger.error(traceback.format_exc())
        try:
            await ws.close()
        except:
            pass

# Async function to process media
async def process_media_async(ws):
    """Process media asynchronously between Twilio and OpenAI."""
    global audio_packets_from_twilio, audio_packets_to_twilio
    
    try:
        logger.info("Connecting to OpenAI Realtime API...")
        logger.debug(f"Using OpenAI API Key: {OPENAI_API_KEY[:5]}...")
        
        # Add connection timeout and retry logic
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with websockets.connect(
                    'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
                    extra_headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "OpenAI-Beta": "realtime=v1"
                    },
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as openai_ws:
                    logger.info("Connected to OpenAI Realtime API successfully")
                    
                    # Send initial session configuration to OpenAI
                    try:
                        await send_session_update(openai_ws)
                        logger.info("Session update sent successfully")
                    except Exception as e:
                        logger.error(f"Failed to send session update: {e}", exc_info=True)
                        retry_count += 1
                        continue
                    
                    stream_sid = None
                    
                    # Create a queue for messages from Twilio
                    twilio_queue = asyncio.Queue()
                    
                    # Function to receive messages from the WebSocket and put them in the queue
                    def ws_receiver():
                        try:
                            logger.info("Starting WebSocket receiver")
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            while True:
                                try:
                                    message = ws.receive()
                                    if message is None:
                                        logger.info("Received None message, closing connection")
                                        break
                                    logger.debug(f"Received message from Twilio: {message[:100]}...")
                                    loop.run_until_complete(twilio_queue.put(message))
                                except Exception as e:
                                    if "Connection closed" in str(e):
                                        logger.info("WebSocket connection closed normally")
                                        break
                                    logger.error(f"Error in ws_receiver loop: {e}", exc_info=True)
                                    break
                        except Exception as e:
                            logger.error(f"Error in ws_receiver: {e}", exc_info=True)
                        finally:
                            try:
                                loop.close()
                            except Exception as e:
                                logger.error(f"Error closing event loop: {e}", exc_info=True)
                    
                    # Start the receiver in a separate thread
                    receiver_thread = threading.Thread(target=ws_receiver)
                    receiver_thread.daemon = True
                    receiver_thread.start()
                    
                    # Function to receive audio from Twilio and send to OpenAI
                    async def receive_from_twilio():
                        """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                        nonlocal stream_sid
                        global audio_packets_from_twilio
                        
                        try:
                            logger.debug("Starting to receive from Twilio")
                            while True:
                                # Get message from queue
                                message = await twilio_queue.get()
                                data = json.loads(message)
                                
                                if data['event'] == 'media' and openai_ws.open:
                                    audio_packets_from_twilio += 1
                                    if audio_packets_from_twilio % 50 == 0:  # Log every 50 packets
                                        logger.debug(f"Received {audio_packets_from_twilio} audio packets from Twilio")
                                    
                                    try:
                                        audio_append = {
                                            "type": "input_audio_buffer.append",
                                            "audio": data['media']['payload']
                                        }
                                        await openai_ws.send(json.dumps(audio_append))
                                        logger.debug("Successfully sent audio to OpenAI")
                                    except Exception as e:
                                        logger.error(f"Error sending audio to OpenAI: {e}", exc_info=True)
                                    
                                elif data['event'] == 'start':
                                    stream_sid = data['start']['streamSid']
                                    logger.info(f"Incoming stream has started with SID: {stream_sid}")
                                    logger.debug(f"Start event data: {data}")
                                    
                                elif data['event'] == 'stop':
                                    logger.info(f"Stream stopped: {stream_sid}")
                                    
                                elif data['event'] == 'connected':
                                    logger.info("Media stream connected event received")
                                    
                                else:
                                    logger.debug(f"Received other event from Twilio: {data['event']}")
                                    
                        except Exception as e:
                            logger.error(f"Error in receive_from_twilio: {e}", exc_info=True)
                            if openai_ws.open:
                                logger.info("Closing OpenAI WebSocket due to error")
                                await openai_ws.close()
                    
                    # Function to receive responses from OpenAI and send to Twilio
                    async def send_to_twilio():
                        """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                        nonlocal stream_sid
                        global audio_packets_to_twilio
                        
                        try:
                            logger.debug("Starting to receive from OpenAI")
                            async for openai_message in openai_ws:
                                response = json.loads(openai_message)
                                
                                # Log all event types for debugging
                                logger.debug(f"Received from OpenAI: {response['type']}")
                                
                                if response['type'] in LOG_EVENT_TYPES:
                                    logger.info(f"OpenAI event: {response['type']}")
                                    if response['type'] == 'response.text.delta' and 'delta' in response:
                                        logger.info(f"OpenAI text: {response['delta']}")
                                    elif response['type'] == 'error':
                                        logger.error(f"OpenAI error: {response}")
                                        
                                if response['type'] == 'session.updated':
                                    logger.info("Session updated successfully with OpenAI")
                                    logger.debug(f"Session update response: {response}")
                                    
                                if response['type'] == 'response.audio.delta' and response.get('delta'):
                                    # Audio from OpenAI
                                    try:
                                        audio_packets_to_twilio += 1
                                        if audio_packets_to_twilio % 10 == 0:  # Log every 10 packets
                                            logger.debug(f"Sent {audio_packets_to_twilio} audio packets to Twilio")
                                        
                                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                                        audio_delta = {
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {
                                                "payload": audio_payload
                                            }
                                        }
                                        ws.send(json.dumps(audio_delta))
                                        logger.debug("Successfully sent audio to Twilio")
                                    except Exception as e:
                                        logger.error(f"Error processing audio data: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Error in send_to_twilio: {e}", exc_info=True)
                    
                    # Run both functions concurrently
                    logger.info("Starting audio streaming between Twilio and OpenAI")
                    await asyncio.gather(receive_from_twilio(), send_to_twilio())
                    break  # If we get here, everything worked
            except Exception as e:
                logger.error(f"Error connecting to OpenAI (attempt {retry_count + 1}/{max_retries}): {e}", exc_info=True)
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(1)  # Wait before retrying
                else:
                    raise  # Re-raise the exception if we've exhausted all retries
    except Exception as e:
        logger.error(f"Error in process_media_async: {e}", exc_info=True)

# Function to send session configuration to OpenAI
async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    logger.info('Sending session update to OpenAI')
    logger.debug(f'Session update data: {session_update}')
    await openai_ws.send(json.dumps(session_update))

# Main function
def main():
    """Main function"""
    logger.info("Starting Twilio-OpenAI server")
    logger.info(f"Using OpenAI voice: {VOICE}")
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == '__main__':
    main() 