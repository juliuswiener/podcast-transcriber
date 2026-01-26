package com.transcriber.app.util

import com.arthenica.ffmpegkit.FFmpegKit
import com.arthenica.ffmpegkit.ReturnCode
import java.io.File

sealed class ConversionResult {
    data class Success(val file: File) : ConversionResult()
    data class Error(val message: String) : ConversionResult()
}

object AudioConverter {

    // Formats natively supported by Whisper API
    private val SUPPORTED_FORMATS = listOf("mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac", "mpeg", "mpga", "oga")

    /**
     * Converts audio file to a format compatible with Whisper API using FFmpeg.
     * Returns ConversionResult.Success with the file (converted or original),
     * or ConversionResult.Error if conversion fails.
     */
    fun convertIfNeeded(inputFile: File, cacheDir: File): ConversionResult {
        val extension = inputFile.extension.lowercase()

        // These formats are natively supported by Whisper - no conversion needed
        if (extension in SUPPORTED_FORMATS) {
            return ConversionResult.Success(inputFile)
        }

        // Convert unsupported formats to MP3 using FFmpeg
        return when (extension) {
            "aac" -> convertToMp3(inputFile, cacheDir, "AAC")
            "opus" -> convertToOgg(inputFile, cacheDir)
            "wma" -> convertToMp3(inputFile, cacheDir, "WMA")
            "amr" -> convertToMp3(inputFile, cacheDir, "AMR")
            "3gp", "3gpp" -> convertToMp3(inputFile, cacheDir, "3GP")
            else -> convertToMp3(inputFile, cacheDir, extension.uppercase())
        }
    }

    /**
     * Converts audio to MP3 format using FFmpeg
     */
    private fun convertToMp3(inputFile: File, cacheDir: File, formatName: String): ConversionResult {
        val outputFile = File(cacheDir, "converted_${System.currentTimeMillis()}.mp3")

        return try {
            // FFmpeg command to convert to MP3
            // -i: input file
            // -vn: no video
            // -acodec libmp3lame: use MP3 encoder
            // -ab 192k: bitrate 192kbps
            // -ar 44100: sample rate 44.1kHz
            // -y: overwrite output
            val command = "-i \"${inputFile.absolutePath}\" -vn -acodec libmp3lame -ab 192k -ar 44100 -y \"${outputFile.absolutePath}\""

            val session = FFmpegKit.execute(command)

            if (ReturnCode.isSuccess(session.returnCode)) {
                ConversionResult.Success(outputFile)
            } else {
                outputFile.delete()
                val errorLog = session.allLogsAsString ?: "Unknown error"
                ConversionResult.Error("Failed to convert $formatName file. FFmpeg error: ${errorLog.take(200)}")
            }
        } catch (e: Exception) {
            outputFile.delete()
            ConversionResult.Error("Failed to convert $formatName file: ${e.message}")
        }
    }

    /**
     * Converts Opus to OGG format using FFmpeg (re-mux without re-encoding)
     */
    private fun convertToOgg(inputFile: File, cacheDir: File): ConversionResult {
        val outputFile = File(cacheDir, "converted_${System.currentTimeMillis()}.ogg")

        return try {
            // Try to just copy the audio stream to OGG container (faster, no quality loss)
            val command = "-i \"${inputFile.absolutePath}\" -vn -acodec copy -y \"${outputFile.absolutePath}\""

            var session = FFmpegKit.execute(command)

            if (ReturnCode.isSuccess(session.returnCode)) {
                return ConversionResult.Success(outputFile)
            }

            // If copy fails, try re-encoding to Vorbis
            val reencodeCommand = "-i \"${inputFile.absolutePath}\" -vn -acodec libvorbis -ab 192k -y \"${outputFile.absolutePath}\""
            session = FFmpegKit.execute(reencodeCommand)

            if (ReturnCode.isSuccess(session.returnCode)) {
                ConversionResult.Success(outputFile)
            } else {
                outputFile.delete()
                ConversionResult.Error("Failed to convert Opus file")
            }
        } catch (e: Exception) {
            outputFile.delete()
            ConversionResult.Error("Failed to convert Opus file: ${e.message}")
        }
    }
}
