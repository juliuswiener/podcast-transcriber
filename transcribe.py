#!/usr/bin/env -S uv run
# /// script
# dependencies = ["openai", "pydub", "audioop-lts"]
# ///
"""Quick and dirty podcast transcriber and summarizer using OpenAI APIs."""

import sys
import os
import argparse
import tempfile
from pathlib import Path
from openai import OpenAI

# 25MB limit for Whisper API
MAX_SIZE = 25 * 1024 * 1024

client = OpenAI()


def split_audio(file_path: str, max_size: int = MAX_SIZE) -> list[str]:
    """Split audio file into chunks under max_size using ffmpeg."""
    from pydub import AudioSegment

    file_size = os.path.getsize(file_path)
    if file_size <= max_size:
        return [file_path]

    print(f"File is {file_size / 1024 / 1024:.1f}MB, splitting into chunks...")

    audio = AudioSegment.from_mp3(file_path)
    duration_ms = len(audio)

    # Estimate chunk duration based on file size ratio
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
        print(f"  Created chunk {i+1}/{num_chunks}")

    return chunks


def transcribe(file_path: str) -> str:
    """Transcribe audio file(s) using Whisper API."""
    chunks = split_audio(file_path)

    full_transcript = []
    for i, chunk_path in enumerate(chunks):
        print(f"Transcribing {'chunk ' + str(i+1) + '/' + str(len(chunks)) if len(chunks) > 1 else 'audio'}...")

        with open(chunk_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
        full_transcript.append(response.text)

        # Clean up temp chunks
        if chunk_path != file_path:
            os.remove(chunk_path)

    return "\n".join(full_transcript)


def summarize(transcript: str, language: str = "English") -> str:
    """Summarize transcript using GPT."""
    print(f"Summarizing in {language}...")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"You are a helpful assistant that summarizes podcast transcripts. Provide a clear, structured summary with key points and main takeaways. Write the summary in {language}."
            },
            {
                "role": "user",
                "content": f"Please summarize this podcast transcript:\n\n{transcript}"
            }
        ]
    )
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser(description="Transcribe and summarize podcasts")
    parser.add_argument("file", help="Audio file (mp3)")
    parser.add_argument("-l", "--language", default="English", help="Summary language (default: English)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    print(f"Processing: {args.file}")
    print(f"File size: {os.path.getsize(args.file) / 1024 / 1024:.1f}MB")
    print()

    # Transcribe
    transcript = transcribe(args.file)

    # Save transcript
    base_name = Path(args.file).stem
    transcript_file = f"{base_name}_transcript.txt"
    with open(transcript_file, "w") as f:
        f.write(transcript)
    print(f"\nTranscript saved to: {transcript_file}")

    # Summarize
    summary = summarize(transcript, args.language)

    # Save summary
    summary_file = f"{base_name}_summary.txt"
    with open(summary_file, "w") as f:
        f.write(summary)
    print(f"Summary saved to: {summary_file}")

    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(summary)


if __name__ == "__main__":
    main()
