"""Podcast transcriber and summarizer web app."""

import os
import tempfile
import json
from typing import Callable, Optional
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, Blueprint, render_template, request, jsonify, Response, stream_with_context
from openai import OpenAI

# 25MB limit for Whisper API
MAX_SIZE = 25 * 1024 * 1024

# History storage
HISTORY_DIR = Path("transcription_history")
HISTORY_FILE = HISTORY_DIR / "history.json"
MAX_HISTORY_ITEMS = 50

client = OpenAI()

transcriber = Blueprint("transcriber", __name__)


def load_history():
    """Load transcription history from file."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading history: {e}")
        return []


def save_history(history):
    """Save transcription history to file."""
    try:
        HISTORY_DIR.mkdir(exist_ok=True)
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")


def add_to_history(source: str, language: str, length: str, transcript: str, summary: str):
    """Add a new transcription to history."""
    history = load_history()

    entry = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "language": language,
        "length": length,
        "transcript": transcript,
        "summary": summary
    }

    # Add to beginning of list
    history.insert(0, entry)

    # Keep only MAX_HISTORY_ITEMS
    if len(history) > MAX_HISTORY_ITEMS:
        history = history[:MAX_HISTORY_ITEMS]

    save_history(history)
    return entry["id"]


def split_audio(file_path: str, max_size: int = MAX_SIZE, status_callback: Optional[Callable[[str], None]] = None) -> list[str]:
    """Split audio file into chunks under max_size using ffmpeg."""
    from pydub import AudioSegment

    print(f"[split_audio] Checking file: {file_path}")
    file_size = os.path.getsize(file_path)
    print(f"[split_audio] File size: {file_size} bytes ({file_size / 1024 / 1024:.1f}MB)")
    print(f"[split_audio] Max chunk size: {max_size} bytes ({max_size / 1024 / 1024:.1f}MB)")

    if file_size <= max_size:
        print(f"[split_audio] File is small enough, no splitting needed")
        return [file_path]

    msg = f"File is {file_size / 1024 / 1024:.1f}MB, splitting into chunks..."
    print(f"[split_audio] {msg}")
    if status_callback:
        status_callback(msg)

    print(f"[split_audio] Loading audio file with pydub...")
    audio = AudioSegment.from_mp3(file_path)
    duration_ms = len(audio)
    print(f"[split_audio] Audio duration: {duration_ms}ms ({duration_ms / 1000 / 60:.1f} minutes)")

    num_chunks = (file_size // max_size) + 1
    chunk_duration_ms = duration_ms // num_chunks
    print(f"[split_audio] Will create {num_chunks} chunks of ~{chunk_duration_ms / 1000:.1f} seconds each")

    chunks = []
    temp_dir = tempfile.mkdtemp()
    print(f"[split_audio] Created temp directory: {temp_dir}")

    for i in range(num_chunks):
        start = i * chunk_duration_ms
        end = min((i + 1) * chunk_duration_ms, duration_ms)
        print(f"[split_audio] Extracting chunk {i+1}/{num_chunks}: {start}ms to {end}ms")
        chunk = audio[start:end]

        chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
        print(f"[split_audio] Exporting chunk to: {chunk_path}")
        chunk.export(chunk_path, format="mp3")
        chunk_size = os.path.getsize(chunk_path)
        print(f"[split_audio] Chunk {i+1} size: {chunk_size / 1024 / 1024:.1f}MB")
        chunks.append(chunk_path)

        msg = f"Created chunk {i+1}/{num_chunks}"
        print(f"[split_audio] {msg}")
        if status_callback:
            status_callback(msg)

    print(f"[split_audio] Successfully created {len(chunks)} chunks")
    return chunks


def transcribe_audio(file_path: str, status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Transcribe audio file(s) using Whisper API."""
    print(f"[transcribe_audio] Starting transcription for: {file_path}")
    chunks = split_audio(file_path, status_callback=status_callback)
    print(f"[transcribe_audio] Processing {len(chunks)} chunk(s)")

    full_transcript = []
    for i, chunk_path in enumerate(chunks):
        msg = f"Transcribing {'chunk ' + str(i+1) + '/' + str(len(chunks)) if len(chunks) > 1 else 'audio'}..."
        print(f"[transcribe_audio] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[transcribe_audio] Opening file: {chunk_path}")
        print(f"[transcribe_audio] Calling OpenAI Whisper API...")
        with open(chunk_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
        transcript_length = len(response.text)
        print(f"[transcribe_audio] Received transcript: {transcript_length} characters")
        print(f"[transcribe_audio] Preview: {response.text[:200]}...")
        full_transcript.append(response.text)

        if chunk_path != file_path:
            print(f"[transcribe_audio] Removing temp chunk: {chunk_path}")
            os.remove(chunk_path)

    total_length = sum(len(t) for t in full_transcript)
    print(f"[transcribe_audio] Transcription complete. Total: {total_length} characters")
    return "\n".join(full_transcript)


LENGTH_PROMPTS = {
    "short": "Provide a brief 2-3 sentence summary with only the main point.",
    "medium": "Provide a clear summary with key points and main takeaways (1-2 paragraphs).",
    "long": "Provide a detailed, comprehensive summary covering all major topics, arguments, and conclusions.",
}

# JSON schema for structured summary output
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "A concise title for the podcast content"
        },
        "summary": {
            "type": "string",
            "description": "The main summary text following the requested length"
        },
        "key_points": {
            "type": "array",
            "description": "List of key points or takeaways",
            "items": {
                "type": "string"
            }
        },
        "topics": {
            "type": "array",
            "description": "Main topics discussed",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["title", "summary", "key_points", "topics"],
    "additionalProperties": False
}


def summarize(transcript: str, language: str = "English", length: str = "medium", status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Summarize transcript using GPT with structured output."""
    print(f"[summarize] Starting summarization")
    print(f"[summarize] Language: {language}, Length: {length}")
    print(f"[summarize] Transcript length: {len(transcript)} characters")
    length_instruction = LENGTH_PROMPTS.get(length, LENGTH_PROMPTS["medium"])
    print(f"[summarize] Length instruction: {length_instruction}")

    msg = f"Generating {length} summary in {language}..."
    print(f"[summarize] {msg}")
    if status_callback:
        status_callback(msg)

    print(f"[summarize] Calling OpenAI GPT-4o-mini API with structured output...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"You are a helpful assistant that summarizes podcast transcripts. {length_instruction} Write the summary in {language}. Provide structured output with a title, summary, key points, and topics."
            },
            {
                "role": "user",
                "content": f"Please summarize this podcast transcript:\n\n{transcript}"
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "podcast_summary",
                "strict": True,
                "schema": SUMMARY_SCHEMA
            }
        }
    )

    print(f"[summarize] Received response from OpenAI")
    print(f"[summarize] Parsing JSON response...")
    # Parse the structured response
    result = json.loads(response.choices[0].message.content)
    print(f"[summarize] Parsed result - Title: {result.get('title', 'N/A')}")
    print(f"[summarize] Key points: {len(result.get('key_points', []))}")
    print(f"[summarize] Topics: {len(result.get('topics', []))}")

    # Format the structured output into a readable text
    print(f"[summarize] Formatting output...")
    formatted_output = f"# {result['title']}\n\n"
    formatted_output += f"{result['summary']}\n\n"

    if result['key_points']:
        formatted_output += "## Key Points\n"
        for point in result['key_points']:
            formatted_output += f"- {point}\n"
        formatted_output += "\n"

    if result['topics']:
        formatted_output += "## Topics Covered\n"
        formatted_output += ", ".join(result['topics'])

    print(f"[summarize] Formatted output length: {len(formatted_output)} characters")
    print(f"[summarize] Summarization complete")
    return formatted_output


@transcriber.route("/")
def index():
    return render_template("index.html")


def download_audio(url: str, status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Download audio from URL to temp file."""
    print(f"[download_audio] Starting download from: {url}")
    msg = f"Downloading audio from URL..."
    print(f"[download_audio] {msg}")
    if status_callback:
        status_callback(msg)

    print(f"[download_audio] Making HTTP GET request...")
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()
    print(f"[download_audio] Response status: {response.status_code}")

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "audio.mp3")
    print(f"[download_audio] Saving to: {file_path}")

    total_size = int(response.headers.get('content-length', 0))
    print(f"[download_audio] Total size: {total_size} bytes ({total_size / 1024 / 1024:.1f}MB)")
    downloaded = 0

    print(f"[download_audio] Starting download stream...")
    with open(file_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0 and status_callback:
                progress = (downloaded / total_size) * 100
                if downloaded % (1024 * 1024) < 8192:  # Update every MB
                    print(f"[download_audio] Progress: {downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB ({progress:.0f}%)")
                    status_callback(f"Downloaded {downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB ({progress:.0f}%)")

    final_size = os.path.getsize(file_path)
    msg = f"Download complete: {final_size / 1024 / 1024:.1f}MB"
    print(f"[download_audio] {msg}")
    if status_callback:
        status_callback(msg)

    return file_path


def process_transcription_from_file(language: str, length: str, file_path: str, filename: str, status_callback: Optional[Callable[[str], None]] = None):
    """Process transcription from a file path (thread-safe)."""
    print(f"[process_transcription_from_file] ===== Starting file processing =====")
    print(f"[process_transcription_from_file] Filename: {filename}")
    print(f"[process_transcription_from_file] File path: {file_path}")
    print(f"[process_transcription_from_file] Language: {language}, Length: {length}")
    try:
        msg = f"Processing uploaded file: {filename}"
        print(f"[process_transcription_from_file] {msg}")
        if status_callback:
            status_callback(msg)

        file_size = os.path.getsize(file_path)
        msg = f"File size: {file_size / 1024 / 1024:.1f}MB"
        print(f"[process_transcription_from_file] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[process_transcription_from_file] Starting transcription...")
        transcript = transcribe_audio(file_path, status_callback)
        print(f"[process_transcription_from_file] Transcription done, starting summarization...")
        summary = summarize(transcript, language, length, status_callback)

        msg = "Processing complete!"
        print(f"[process_transcription_from_file] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[process_transcription_from_file] Saving to history...")
        # Save to history
        history_id = add_to_history(filename, language, length, transcript, summary)

        msg = f"Saved to history (ID: {history_id})"
        print(f"[process_transcription_from_file] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[process_transcription_from_file] ===== Processing complete =====")
        return {
            "transcript": transcript,
            "summary": summary,
            "history_id": history_id
        }
    except Exception as e:
        print(f"[process_transcription_from_file] ERROR: {type(e).__name__}: {e}")
        import traceback
        print(f"[process_transcription_from_file] Traceback:")
        traceback.print_exc()
        raise


def process_transcription_from_url(language: str, length: str, url: str, status_callback: Optional[Callable[[str], None]] = None):
    """Process transcription from a URL (thread-safe)."""
    print(f"[process_transcription_from_url] ===== Starting URL processing =====")
    print(f"[process_transcription_from_url] URL: {url}")
    print(f"[process_transcription_from_url] Language: {language}, Length: {length}")
    file_path = None
    try:
        print(f"[process_transcription_from_url] Downloading audio...")
        file_path = download_audio(url, status_callback)

        print(f"[process_transcription_from_url] Starting transcription...")
        transcript = transcribe_audio(file_path, status_callback)
        print(f"[process_transcription_from_url] Transcription done, starting summarization...")
        summary = summarize(transcript, language, length, status_callback)

        msg = "Processing complete!"
        print(f"[process_transcription_from_url] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[process_transcription_from_url] Saving to history...")
        # Save to history
        history_id = add_to_history(url, language, length, transcript, summary)

        msg = f"Saved to history (ID: {history_id})"
        print(f"[process_transcription_from_url] {msg}")
        if status_callback:
            status_callback(msg)

        print(f"[process_transcription_from_url] ===== Processing complete =====")
        return {
            "transcript": transcript,
            "summary": summary,
            "history_id": history_id
        }
    except Exception as e:
        print(f"[process_transcription_from_url] ERROR: {type(e).__name__}: {e}")
        import traceback
        print(f"[process_transcription_from_url] Traceback:")
        traceback.print_exc()
        raise
    finally:
        if file_path and os.path.exists(file_path):
            print(f"[process_transcription_from_url] Cleaning up temp file: {file_path}")
            os.remove(file_path)


def process_transcription(language: str, length: str, url: str, file, status_callback: Optional[Callable[[str], None]] = None):
    """Core transcription processing logic (for non-streaming endpoint)."""
    temp_dir = tempfile.mkdtemp()
    file_path = None
    source_name = None

    try:
        if url:
            file_path = download_audio(url, status_callback)
            source_name = url
        elif file and file.filename:
            msg = f"Saving uploaded file: {file.filename}"
            print(msg)
            if status_callback:
                status_callback(msg)
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
            source_name = file.filename
            msg = f"File saved: {os.path.getsize(file_path) / 1024 / 1024:.1f}MB"
            print(msg)
            if status_callback:
                status_callback(msg)
        else:
            raise ValueError("No file or URL provided")

        transcript = transcribe_audio(file_path, status_callback)
        summary = summarize(transcript, language, length, status_callback)

        msg = "Processing complete!"
        print(msg)
        if status_callback:
            status_callback(msg)

        # Save to history
        history_id = add_to_history(source_name, language, length, transcript, summary)

        msg = f"Saved to history (ID: {history_id})"
        print(msg)
        if status_callback:
            status_callback(msg)

        return {
            "transcript": transcript,
            "summary": summary,
            "history_id": history_id
        }
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@transcriber.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    """Standard JSON endpoint for transcription."""
    language = request.form.get("language", "English")
    length = request.form.get("length", "medium")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")

    try:
        result = process_transcription(language, length, url, file)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to download: {e}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@transcriber.route("/transcribe-stream", methods=["POST"])
def transcribe_stream_endpoint():
    """SSE endpoint for transcription with status updates."""
    print(f"[transcribe_stream_endpoint] ===== New SSE request received =====")
    language = request.form.get("language", "English")
    length = request.form.get("length", "medium")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")
    print(f"[transcribe_stream_endpoint] Parameters: language={language}, length={length}")
    print(f"[transcribe_stream_endpoint] URL: {url if url else 'None'}")
    print(f"[transcribe_stream_endpoint] File: {file.filename if file and file.filename else 'None'}")

    # Save file to temp location before threading (Flask file objects don't work across threads)
    saved_file_path = None
    if file and file.filename:
        print(f"[transcribe_stream_endpoint] Saving uploaded file before threading...")
        temp_dir = tempfile.mkdtemp()
        saved_file_path = os.path.join(temp_dir, file.filename)
        file.save(saved_file_path)
        file_size = os.path.getsize(saved_file_path)
        print(f"[transcribe_stream_endpoint] File saved to: {saved_file_path} ({file_size / 1024 / 1024:.1f}MB)")

    def generate():
        """Generator for SSE stream."""
        print(f"[generate] Starting SSE generator")
        import threading
        import queue

        message_queue = queue.Queue()

        def callback_wrapper(message: str):
            """Queue messages to be sent."""
            print(f"[generate] Queueing message: {message}")
            message_queue.put(message)

        # Send initial status
        print(f"[generate] Sending initial status message")
        yield f"data: {json.dumps({'status': 'Starting transcription...'})}\n\n"

        # Process in thread to allow yielding during processing
        result_holder = {}
        error_holder = {}

        def process():
            print(f"[generate:process] Thread started")
            try:
                # Pass file path instead of file object for threaded processing
                if saved_file_path:
                    print(f"[generate:process] Processing file: {saved_file_path}")
                    result_holder['data'] = process_transcription_from_file(
                        language, length, saved_file_path, file.filename, callback_wrapper
                    )
                elif url:
                    print(f"[generate:process] Processing URL: {url}")
                    result_holder['data'] = process_transcription_from_url(
                        language, length, url, callback_wrapper
                    )
                else:
                    print(f"[generate:process] ERROR: No file or URL provided")
                    raise ValueError("No file or URL provided")
            except Exception as e:
                print(f"[generate:process] ERROR in thread: {type(e).__name__}: {e}")
                error_holder['error'] = e
            finally:
                print(f"[generate:process] Thread complete, sending done signal")
                message_queue.put(None)  # Signal completion
                # Clean up temp file
                if saved_file_path and os.path.exists(saved_file_path):
                    try:
                        os.remove(saved_file_path)
                        os.rmdir(os.path.dirname(saved_file_path))
                    except:
                        pass

        print(f"[generate] Starting worker thread")
        thread = threading.Thread(target=process)
        thread.start()

        # Yield messages as they come
        print(f"[generate] Entering message loop")
        message_count = 0
        while True:
            try:
                message = message_queue.get(timeout=0.1)
                if message is None:  # Done signal
                    print(f"[generate] Received done signal after {message_count} messages")
                    break
                message_count += 1
                print(f"[generate] Yielding message {message_count}: {message[:100]}...")
                yield f"data: {json.dumps({'status': message})}\n\n"
            except queue.Empty:
                # Send keepalive to prevent timeout
                yield ": keepalive\n\n"

        print(f"[generate] Waiting for thread to join...")
        thread.join()
        print(f"[generate] Thread joined")

        # Check for errors
        if 'error' in error_holder:
            e = error_holder['error']
            print(f"[generate] Error occurred: {type(e).__name__}: {e}")
            if isinstance(e, ValueError):
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            elif isinstance(e, requests.RequestException):
                yield f"data: {json.dumps({'error': f'Failed to download: {e}'})}\n\n"
            else:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        else:
            # Send final result
            print(f"[generate] Sending final result")
            yield f"data: {json.dumps({'status': 'Complete', 'result': result_holder['data']})}\n\n"

        print(f"[generate] Generator complete")

    print(f"[transcribe_stream_endpoint] Creating SSE response")
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    print(f"[transcribe_stream_endpoint] Returning response")
    return response


@transcriber.route("/history", methods=["GET"])
def get_history():
    """Get transcription history."""
    try:
        history = load_history()
        # Return summary info only (not full transcripts) for list view
        summary_list = [
            {
                "id": item["id"],
                "timestamp": item["timestamp"],
                "source": item["source"],
                "language": item["language"],
                "length": item["length"],
                "preview": item["summary"][:200] + "..." if len(item["summary"]) > 200 else item["summary"]
            }
            for item in history
        ]
        return jsonify(summary_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@transcriber.route("/history/<history_id>", methods=["GET"])
def get_history_item(history_id):
    """Get a specific transcription from history."""
    try:
        history = load_history()
        for item in history:
            if item["id"] == history_id:
                return jsonify(item)
        return jsonify({"error": "History item not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload
    app.register_blueprint(transcriber)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
