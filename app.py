"""Podcast transcriber and summarizer web app."""

import os
import tempfile

import requests
from flask import Flask, Blueprint, render_template, request, jsonify
from openai import OpenAI

# 25MB limit for Whisper API
MAX_SIZE = 25 * 1024 * 1024

client = OpenAI()

transcriber = Blueprint("transcriber", __name__)


def split_audio(file_path: str, max_size: int = MAX_SIZE) -> list[str]:
    """Split audio file into chunks under max_size using ffmpeg."""
    from pydub import AudioSegment

    file_size = os.path.getsize(file_path)
    if file_size <= max_size:
        return [file_path]

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

    return chunks


def transcribe_audio(file_path: str) -> str:
    """Transcribe audio file(s) using Whisper API."""
    chunks = split_audio(file_path)

    full_transcript = []
    for chunk_path in chunks:
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


def summarize(transcript: str, language: str = "English", length: str = "medium") -> str:
    """Summarize transcript using GPT."""
    length_instruction = LENGTH_PROMPTS.get(length, LENGTH_PROMPTS["medium"])

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


def download_audio(url: str) -> str:
    """Download audio from URL to temp file."""
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, "audio.mp3")

    with open(file_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return file_path


@transcriber.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    language = request.form.get("language", "English")
    length = request.form.get("length", "medium")
    url = request.form.get("url", "").strip()
    file = request.files.get("file")

    temp_dir = tempfile.mkdtemp()
    file_path = None

    try:
        if url:
            file_path = download_audio(url)
        elif file and file.filename:
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
        else:
            return jsonify({"error": "No file or URL provided"}), 400

        transcript = transcribe_audio(file_path)
        summary = summarize(transcript, language, length)

        return jsonify({
            "transcript": transcript,
            "summary": summary
        })
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to download: {e}"}), 400
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload
    app.register_blueprint(transcriber)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
