package com.transcriber.app.ui

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.transcriber.app.service.AudioRecorder
import com.transcriber.app.service.TranscriptionService
import com.transcriber.app.service.TranscriptionState
import com.transcriber.app.util.AudioConverter
import com.transcriber.app.util.PreferencesManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File

data class TranscriberUiState(
    val apiKey: String = "",
    val isRecording: Boolean = false,
    val transcriptionState: TranscriptionState = TranscriptionState.Idle
)

class TranscriberViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(TranscriberUiState())
    val uiState: StateFlow<TranscriberUiState> = _uiState.asStateFlow()

    private var audioRecorder: AudioRecorder? = null
    private var recordingFile: File? = null

    private val transcriptionService = TranscriptionService()

    fun updateApiKey(apiKey: String) {
        _uiState.update { it.copy(apiKey = apiKey) }
    }

    fun startRecording(context: Context) {
        viewModelScope.launch {
            try {
                val outputFile = File(context.cacheDir, "recording_${System.currentTimeMillis()}.m4a")
                audioRecorder = AudioRecorder(context).apply {
                    start(outputFile)
                }
                recordingFile = outputFile
                _uiState.update { it.copy(isRecording = true) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isRecording = false,
                        transcriptionState = TranscriptionState.Error("Failed to start recording: ${e.message}")
                    )
                }
            }
        }
    }

    fun stopRecording(context: Context) {
        viewModelScope.launch {
            try {
                audioRecorder?.stop()
                audioRecorder = null
                _uiState.update { it.copy(isRecording = false) }

                recordingFile?.let { file ->
                    if (file.exists() && file.length() > 0) {
                        transcribeAudioFile(file)
                    } else {
                        _uiState.update {
                            it.copy(transcriptionState = TranscriptionState.Error("Recording file is empty"))
                        }
                    }
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isRecording = false,
                        transcriptionState = TranscriptionState.Error("Failed to stop recording: ${e.message}")
                    )
                }
            }
        }
    }

    fun transcribeFile(context: Context, uri: Uri) {
        viewModelScope.launch {
            _uiState.update { it.copy(transcriptionState = TranscriptionState.Loading) }

            var tempFile: File? = null
            var convertedFile: File? = null

            try {
                // Get the original file extension from the URI
                val extension = getFileExtension(context, uri)

                // Copy file to cache directory with proper extension
                val inputStream = context.contentResolver.openInputStream(uri)
                tempFile = File(context.cacheDir, "audio_${System.currentTimeMillis()}.$extension")

                inputStream?.use { input ->
                    tempFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }

                // Convert if needed (AAC -> M4A, etc.)
                convertedFile = AudioConverter.convertIfNeeded(tempFile, context.cacheDir)

                transcribeAudioFile(convertedFile)
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(transcriptionState = TranscriptionState.Error("Failed to read file: ${e.message}"))
                }
            } finally {
                // Clean up temp files
                tempFile?.delete()
                if (convertedFile != tempFile) {
                    convertedFile?.delete()
                }
            }
        }
    }

    private fun getFileExtension(context: Context, uri: Uri): String {
        // Try to get extension from content resolver
        val mimeType = context.contentResolver.getType(uri)
        val extensionFromMime = when (mimeType) {
            "audio/mpeg", "audio/mp3" -> "mp3"
            "audio/mp4", "audio/m4a", "audio/x-m4a" -> "m4a"
            "audio/wav", "audio/x-wav" -> "wav"
            "audio/ogg", "audio/vorbis", "application/ogg" -> "ogg"
            "audio/opus", "application/opus" -> "opus"
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/webm" -> "webm"
            "audio/aac", "audio/x-aac" -> "aac"
            else -> null
        }

        if (extensionFromMime != null) return extensionFromMime

        // Try to get from the URI path or display name
        val path = uri.path ?: ""
        val lastDot = path.lastIndexOf('.')
        if (lastDot >= 0 && lastDot < path.length - 1) {
            return path.substring(lastDot + 1).lowercase()
        }

        // Default to mp3 if we can't determine
        return "mp3"
    }

    private suspend fun transcribeAudioFile(file: File) {
        _uiState.update { it.copy(transcriptionState = TranscriptionState.Loading) }

        val apiKey = _uiState.value.apiKey
        if (apiKey.isBlank()) {
            _uiState.update {
                it.copy(transcriptionState = TranscriptionState.Error("Please enter your OpenAI API key"))
            }
            return
        }

        val result = transcriptionService.transcribe(file, apiKey)
        _uiState.update { it.copy(transcriptionState = result) }
    }

    override fun onCleared() {
        super.onCleared()
        audioRecorder?.stop()
        recordingFile?.delete()
    }
}
