package com.transcriber.app.service

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

sealed class TranscriptionState {
    data object Idle : TranscriptionState()
    data object Loading : TranscriptionState()
    data class Success(val text: String) : TranscriptionState()
    data class Error(val message: String) : TranscriptionState()
}

class TranscriptionService {

    private val client = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    suspend fun transcribe(audioFile: File, apiKey: String): TranscriptionState {
        return withContext(Dispatchers.IO) {
            try {
                // Check file size - OpenAI Whisper API has a 25MB limit
                val fileSizeInMB = audioFile.length() / (1024 * 1024)
                if (fileSizeInMB > 25) {
                    return@withContext TranscriptionState.Error(
                        "File too large (${fileSizeInMB}MB). Maximum size is 25MB."
                    )
                }

                val extension = audioFile.extension.lowercase()
                val mediaType = getMediaType(extension)

                // Use a filename with proper extension for Whisper to recognize
                val filename = getFilenameForWhisper(extension)

                val requestBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        "file",
                        filename,
                        audioFile.asRequestBody(mediaType.toMediaType())
                    )
                    .addFormDataPart("model", "whisper-1")
                    .build()

                val request = Request.Builder()
                    .url("https://api.openai.com/v1/audio/transcriptions")
                    .header("Authorization", "Bearer $apiKey")
                    .post(requestBody)
                    .build()

                val response = client.newCall(request).execute()

                if (!response.isSuccessful) {
                    val errorBody = response.body?.string() ?: "Unknown error"
                    val errorMessage = try {
                        val json = JSONObject(errorBody)
                        json.optJSONObject("error")?.optString("message") ?: errorBody
                    } catch (e: Exception) {
                        errorBody
                    }
                    return@withContext TranscriptionState.Error("API Error: $errorMessage")
                }

                val responseBody = response.body?.string() ?: ""
                val json = JSONObject(responseBody)
                val text = json.optString("text", "")

                if (text.isBlank()) {
                    TranscriptionState.Error("No transcription returned")
                } else {
                    TranscriptionState.Success(text)
                }
            } catch (e: Exception) {
                TranscriptionState.Error("Transcription failed: ${e.message}")
            }
        }
    }

    private fun getMediaType(extension: String): String {
        return when (extension) {
            "mp3" -> "audio/mpeg"
            "mp4", "m4a", "aac" -> "audio/mp4"  // AAC needs mp4 container type
            "wav" -> "audio/wav"
            "webm" -> "audio/webm"
            "ogg", "oga", "opus" -> "audio/ogg"  // Opus uses ogg container
            "flac" -> "audio/flac"
            else -> "application/octet-stream"
        }
    }

    // Whisper expects specific extensions - map to supported ones
    private fun getFilenameForWhisper(extension: String): String {
        val whisperExtension = when (extension) {
            "opus" -> "ogg"  // Send opus as ogg
            "oga" -> "ogg"
            "aac" -> "m4a"   // Send aac as m4a
            else -> extension
        }
        return "audio.$whisperExtension"
    }
}
