"""Podcast transcriber and summarizer web app."""

import os
import tempfile
import json
from typing import Callable, Optional

import requests
from flask import Flask, Blueprint, render_template, request, jsonify, Response, stream_with_context
from openai import OpenAI

# 25MB limit for Whisper API
MAX_SIZE = 25 * 1024 * 1024

client = OpenAI()

transcriber = Blueprint("transcriber", __name__)


def split_audio(file_path: str, max_size: int = MAX_SIZE, status_callback: Optional[Callable[[str], None]] = None) -> list[str]:
    """Split audio file into chunks under max_size using ffmpeg."""
    from pydub import AudioSegment

    file_size = os.path.getsize(file_path)
    if file_size <= max_size:
        return [file_path]

    msg = f"File is {file_size / 1024 / 1024:.1f}MB, splitting into chunks..."
    print(msg)
    if status_callback:
        status_callback(msg)

    audio = AudioSegment.from_mp3(file_path)
    duration_ms = len(audio)

    num_chunks = (file_size // max_size) + 1
    chunk_duration_ms = duration_ms // num_chunks

    chunks = []
    temp_dir = tempfile.mkdtemp()

    for i in range(num_chunks):
        start = i * chunk_duration_ms
        end = min((i + 1) * chunk_duration_ms, duration_ms)
        chunk = audio[start:end]

        chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)

        msg = f"Created chunk {i+1}/{num_chunks}"
        print(f"  {msg}")
        if status_callback:
            status_callback(msg)

    return chunks


def transcribe_audio(file_path: str, status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Transcribe audio file(s) using Whisper API."""
    chunks = split_audio(file_path, status_callback=status_callback)

    full_transcript = []
    for i, chunk_path in enumerate(chunks):
        msg = f"Transcribing {'chunk ' + str(i+1) + '/' + str(len(chunks)) if len(chunks) > 1 else 'audio'}..."
        print(msg)
        if status_callback:
            status_callback(msg)

        with open(chunk_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
        full_transcript.append(response.text)

        if chunk_path != file_path:
            os.remove(chunk_path)

    return "\n".join(full_transcript)


LENGTH_PROMPTS = {
    "short": "Provide a brief 2-3 sentence summary with only the main point.",
    "medium": "Provide a clear summary with key points and main takeaways (1-2 paragraphs).",
    "long": "Provide a detailed, comprehensive summary covering all major topics, arguments, and conclusions.",
}


def summarize(transcript: str, language: str = "English", length: str = "medium", status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Summarize transcript using GPT."""
    length_instruction = LENGTH_PROMPTS.get(length, LENGTH_PROMPTS["medium"])

    msg = f"Generating {length} summary in {language}..."
    print(msg)
    if status_callback:
        status_callback(msg)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"You are a helpful assistant that summarizes podcast transcripts. {length_instruction} Write the summary in {language}."
            },
            {
                "role": "user",
                "content": f"Please summarize this podcast transcript:\n\n{transcript}"
            }
        ]
    )
    return response.choices[0].message.content


@transcriber.route("/")
def index():
    return render_template("index.html")


def download_audio(url: str, status_callback: Optional[Callable[[str], None]] = None) -> str:
    """Download audio from URL to temp file."""
    msg = f"Downloading audio from URL..."
    print(msg)
    if status_callback:
        status_callback(msg)

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "audio.mp3")

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0

    with open(file_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0 and status_callback:
                progress = (downloaded / total_size) * 100
                if downloaded % (1024 * 1024) < 8192:  # Update every MB
                    status_callback(f"Downloaded {downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB ({progress:.0f}%)")

    msg = f"Download complete: {os.path.getsize(file_path) / 1024 / 1024:.1f}MB"
    print(msg)
    if status_callback:
        status_callback(msg)

    return file_path


def process_transcription(language: str, length: str, url: str, file, status_callback: Optional[Callable[[str], None]] = None):
    """Core transcription processing logic."""
    temp_dir = tempfile.mkdtemp()
    file_path = None

    try:
        if url:
            file_path = download_audio(url, status_callback)
        elif file and file.filename:
            msg = f"Saving uploaded file: {file.filename}"
            print(msg)
            if status_callback:
                status_callback(msg)
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
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

        return {
            "transcript": transcript,
            "summary": summary
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
    language = request.form.get("language", "English")
    length = request.form.get("length", "medium")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")

    def generate():
        """Generator for SSE stream."""
        status_messages = []

        def status_callback(message: str):
            """Collect status message."""
            status_messages.append(message)

        try:
            # Send initial status
            yield f"data: {json.dumps({'status': 'Starting transcription...'})}\n\n"

            # Create a wrapper to send messages as they're generated
            import threading
            import queue
            message_queue = queue.Queue()

            def callback_wrapper(message: str):
                message_queue.put(message)
                status_callback(message)

            # Process in thread to allow yielding during processing
            result_holder = {}
            error_holder = {}

            def process():
                try:
                    result_holder['data'] = process_transcription(language, length, url, file, callback_wrapper)
                except Exception as e:
                    error_holder['error'] = e
                finally:
                    message_queue.put(None)  # Signal completion

            thread = threading.Thread(target=process)
            thread.start()

            # Yield messages as they come
            while True:
                try:
                    message = message_queue.get(timeout=0.1)
                    if message is None:  # Done signal
                        break
                    yield f"data: {json.dumps({'status': message})}\n\n"
                except queue.Empty:
                    continue

            thread.join()

            # Check for errors
            if 'error' in error_holder:
                e = error_holder['error']
                if isinstance(e, ValueError):
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                elif isinstance(e, requests.RequestException):
                    yield f"data: {json.dumps({'error': f'Failed to download: {e}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
            else:
                # Send final result
                yield f"data: {json.dumps({'status': 'Complete', 'result': result_holder['data']})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload
    app.register_blueprint(transcriber)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
