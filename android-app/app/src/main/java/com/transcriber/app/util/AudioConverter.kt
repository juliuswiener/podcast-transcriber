package com.transcriber.app.util

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.File
import java.nio.ByteBuffer

sealed class ConversionResult {
    data class Success(val file: File) : ConversionResult()
    data class Error(val message: String) : ConversionResult()
}

object AudioConverter {

    // Formats natively supported by Whisper API
    private val SUPPORTED_FORMATS = listOf("mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac", "mpeg", "mpga", "oga")

    /**
     * Converts audio file to a format compatible with Whisper API.
     * Returns ConversionResult.Success with the file (converted or original),
     * or ConversionResult.Error if the format is not supported.
     */
    fun convertIfNeeded(inputFile: File, cacheDir: File): ConversionResult {
        val extension = inputFile.extension.lowercase()

        // These formats are natively supported by Whisper
        if (extension in SUPPORTED_FORMATS) {
            return ConversionResult.Success(inputFile)
        }

        // AAC and Opus need conversion
        return when (extension) {
            "aac" -> convertAacToM4a(inputFile, cacheDir)
            "opus" -> convertOpusToOgg(inputFile, cacheDir)
            else -> ConversionResult.Error(
                "Unsupported format: .$extension. Supported formats: ${SUPPORTED_FORMATS.joinToString(", ") { ".$it" }}"
            )
        }
    }

    /**
     * Attempts to convert AAC to M4A using MediaMuxer.
     * This works for AAC files that are already in a container (like ADTS).
     */
    private fun convertAacToM4a(inputFile: File, cacheDir: File): ConversionResult {
        val outputFile = File(cacheDir, "converted_${System.currentTimeMillis()}.m4a")

        try {
            val extractor = MediaExtractor()
            extractor.setDataSource(inputFile.absolutePath)

            // Find the audio track
            var audioTrackIndex = -1
            var audioFormat: MediaFormat? = null

            for (i in 0 until extractor.trackCount) {
                val format = extractor.getTrackFormat(i)
                val mime = format.getString(MediaFormat.KEY_MIME)
                if (mime?.startsWith("audio/") == true) {
                    audioTrackIndex = i
                    audioFormat = format
                    break
                }
            }

            if (audioTrackIndex == -1 || audioFormat == null) {
                extractor.release()
                outputFile.delete()
                return ConversionResult.Error(
                    "Cannot process this AAC file. Please convert it to MP3 or M4A using a converter app first."
                )
            }

            extractor.selectTrack(audioTrackIndex)

            // Create muxer
            val muxer = MediaMuxer(outputFile.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            val muxerTrackIndex = muxer.addTrack(audioFormat)
            muxer.start()

            // Copy data
            val buffer = ByteBuffer.allocate(1024 * 1024) // 1MB buffer
            val bufferInfo = MediaCodec.BufferInfo()

            while (true) {
                val sampleSize = extractor.readSampleData(buffer, 0)
                if (sampleSize < 0) break

                bufferInfo.offset = 0
                bufferInfo.size = sampleSize
                bufferInfo.presentationTimeUs = extractor.sampleTime
                bufferInfo.flags = extractor.sampleFlags

                muxer.writeSampleData(muxerTrackIndex, buffer, bufferInfo)
                extractor.advance()
            }

            muxer.stop()
            muxer.release()
            extractor.release()

            return ConversionResult.Success(outputFile)
        } catch (e: Exception) {
            outputFile.delete()
            return ConversionResult.Error(
                "Cannot convert AAC file: ${e.message}. Please convert it to MP3 or M4A using a converter app first."
            )
        }
    }

    /**
     * For Opus files, copy with .ogg extension since Opus is typically in OGG container
     */
    private fun convertOpusToOgg(inputFile: File, cacheDir: File): ConversionResult {
        val outputFile = File(cacheDir, "converted_${System.currentTimeMillis()}.ogg")
        return try {
            inputFile.copyTo(outputFile, overwrite = true)
            ConversionResult.Success(outputFile)
        } catch (e: Exception) {
            outputFile.delete()
            ConversionResult.Error("Failed to process Opus file: ${e.message}")
        }
    }
}
