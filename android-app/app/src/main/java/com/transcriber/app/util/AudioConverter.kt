package com.transcriber.app.util

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.File
import java.nio.ByteBuffer

object AudioConverter {

    /**
     * Converts audio file to a format compatible with Whisper API.
     * Returns the converted file, or the original file if no conversion needed.
     */
    fun convertIfNeeded(inputFile: File, cacheDir: File): File {
        val extension = inputFile.extension.lowercase()

        // These formats are natively supported by Whisper
        if (extension in listOf("mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac", "mpeg", "mpga")) {
            return inputFile
        }

        // AAC and Opus need conversion
        return when (extension) {
            "aac" -> convertToM4a(inputFile, cacheDir)
            "opus" -> convertToOgg(inputFile, cacheDir)
            else -> inputFile
        }
    }

    /**
     * Wraps raw AAC audio into an M4A container using MediaMuxer
     */
    private fun convertToM4a(inputFile: File, cacheDir: File): File {
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
                // Can't extract audio, return original
                extractor.release()
                return inputFile
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

            return outputFile
        } catch (e: Exception) {
            // If conversion fails, return original file
            outputFile.delete()
            return inputFile
        }
    }

    /**
     * For Opus files, we just rename to .ogg since Opus is typically in OGG container
     * and Whisper supports OGG natively
     */
    private fun convertToOgg(inputFile: File, cacheDir: File): File {
        // Opus files are usually already in OGG container, just copy with .ogg extension
        val outputFile = File(cacheDir, "converted_${System.currentTimeMillis()}.ogg")
        try {
            inputFile.copyTo(outputFile, overwrite = true)
            return outputFile
        } catch (e: Exception) {
            outputFile.delete()
            return inputFile
        }
    }
}
