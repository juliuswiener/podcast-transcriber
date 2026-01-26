package com.transcriber.app.ui

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.transcriber.app.service.AudioRecorder
import com.transcriber.app.service.TranscriptionService
import com.transcriber.app.service.TranscriptionState
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

            try {
                // Copy file to cache directory
                val inputStream = context.contentResolver.openInputStream(uri)
                val tempFile = File(context.cacheDir, "audio_${System.currentTimeMillis()}.tmp")

                inputStream?.use { input ->
                    tempFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }

                transcribeAudioFile(tempFile)

                // Clean up temp file after transcription
                tempFile.delete()
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(transcriptionState = TranscriptionState.Error("Failed to read file: ${e.message}"))
                }
            }
        }
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
