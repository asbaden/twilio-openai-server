# Twilio OpenAI Server

A server that integrates Twilio with OpenAI to create an AI voice assistant.

## Setup

1. Clone this repository
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file based on `.env.example` and add your API keys:
   ```
   cp .env.example .env
   # Edit .env with your actual API keys
   ```
5. Run the server:
   ```
   python twilio_openai_server.py
   ```

## Deployment

### Local Development with ngrok

For local development, you can use ngrok to expose your local server:

```
ngrok http 8080
```

Then update your Twilio phone number's voice URL to point to your ngrok URL + `/voice`.

### Cloud Deployment

For production, deploy this server to a cloud platform like Render:

1. Push this repository to GitHub
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Configure the service:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python twilio_openai_server.py`
5. Add your environment variables in the Render dashboard
6. Update your Twilio phone number's voice URL to point to your Render URL + `/voice`

## How It Works

1. **Incoming Call**: When a call comes in, Twilio routes it to this server.
2. **Media Streaming**: The server establishes a WebSocket connection with Twilio to receive real-time audio from the call.
3. **Speech-to-Text**: The audio is transcribed using OpenAI's Whisper API.
4. **AI Response**: The transcription is sent to OpenAI's GPT-4o to generate a response.
5. **Text-to-Speech**: The AI response is converted to speech using OpenAI's TTS API.
6. **Response Playback**: The speech is played back to the caller.

## Testing

1. Call your Twilio phone number
2. You should hear the welcome message
3. Speak and the AI should respond

## Limitations and Next Steps

- The current implementation doesn't fully support playing back the AI's response to the caller. This would require implementing a way to stream the TTS audio back to the call.
- For production use, you would need to deploy this server to a cloud provider with a stable public URL.
- Consider adding authentication to secure your endpoints.
- Implement error handling and retry logic for more robust operation.
- Add logging and monitoring for production use.

## Troubleshooting

- **WebSocket Connection Issues**: Make sure your server is publicly accessible and the URL in the TwiML response is correct.
- **Audio Processing Issues**: Check that the audio format conversion is working correctly.
- **OpenAI API Issues**: Verify your API key and check the OpenAI status page for any service disruptions.
- **Twilio Issues**: Check the Twilio console for error messages and verify your webhook URLs. 