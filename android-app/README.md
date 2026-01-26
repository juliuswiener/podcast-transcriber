# Voice Transcriber - Android App

An Android app for transcribing audio using OpenAI's Whisper API. You can either record audio directly using your device's microphone or select an existing audio file to transcribe.

## Features

- **Voice Recording**: Record audio directly from your device's microphone
- **File Import**: Select audio files (MP3, M4A, WAV, etc.) from your device
- **OpenAI Whisper**: Uses OpenAI's Whisper API for accurate transcription
- **Copy to Clipboard**: Easily copy transcribed text

## Requirements

- Android 8.0 (API 26) or higher
- OpenAI API key (get one at https://platform.openai.com)
- Internet connection for transcription

## Building the APK

### Prerequisites

- Android Studio Arctic Fox or newer (recommended)
- OR JDK 17+ and Android SDK

### Using Android Studio

1. Open Android Studio
2. Select "Open an existing project"
3. Navigate to the `android-app` directory
4. Wait for Gradle sync to complete
5. Build > Build Bundle(s) / APK(s) > Build APK(s)
6. The APK will be in `app/build/outputs/apk/debug/`

### Using Command Line

```bash
# Navigate to android-app directory
cd android-app

# Build debug APK (Unix/Mac)
./gradlew assembleDebug

# Build debug APK (Windows)
gradlew.bat assembleDebug

# The APK will be at app/build/outputs/apk/debug/app-debug.apk
```

## Installing the APK

### Via ADB
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Manual Installation
1. Transfer the APK to your Android device
2. Open the APK file on your device
3. Enable "Install from unknown sources" if prompted
4. Complete the installation

## Usage

1. **Enter API Key**: On first launch, enter your OpenAI API key
2. **Grant Permissions**: Allow microphone access when prompted
3. **Record or Select**:
   - Tap the microphone button to start recording
   - Tap again to stop and transcribe
   - OR tap the file button to select an existing audio file
4. **View Results**: The transcription will appear below
5. **Copy**: Use the copy button to copy the transcription

## Supported Audio Formats

- MP3
- M4A/MP4
- WAV
- WEBM
- OGG
- FLAC

**Note**: Files must be under 25MB (OpenAI Whisper API limit).

## Privacy

- Your API key is stored locally on your device
- Audio files are sent to OpenAI for transcription
- No data is stored on external servers by this app

## Tech Stack

- **Language**: Kotlin
- **UI**: Jetpack Compose with Material 3
- **Networking**: OkHttp
- **Architecture**: MVVM with StateFlow
