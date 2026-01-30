package org.blindmasters.StMic

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.min

class AudioEngine {

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var agc: AutomaticGainControl? = null
    
    private var outputStream: OutputStream? = null

    private var recordJob: Job? = null
    var isRunning = false
        private set

    // Configuration
    var gainFactor: Float = 1.0f
    var useStereo: Boolean = false
    var enableNS: Boolean = false
    var enableAGC: Boolean = false
    var selectedSource: Int = MediaRecorder.AudioSource.MIC
    var muteLocal: Boolean = false
    
    fun setStream(stream: OutputStream?) {
        this.outputStream = stream
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRunning) return
        isRunning = true

        val sampleRate = 48000
        val channelConfigIn = if (useStereo) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
        val channelConfigOut = if (useStereo) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT

        val minBufSize = AudioRecord.getMinBufferSize(sampleRate, channelConfigIn, audioFormat)
        // Use a slightly larger buffer to be safe, or exact for latency.
        // For passthrough, smaller is better for latency, but riskier for underruns.
        val bufferSize = max(minBufSize, 4096) 
        val trackBufferSize = AudioTrack.getMinBufferSize(sampleRate, channelConfigOut, audioFormat)

        try {
            audioRecord = AudioRecord(
                selectedSource,
                sampleRate,
                channelConfigIn,
                audioFormat,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e("AudioEngine", "AudioRecord initialization failed")
                isRunning = false
                return
            }

            // Apply Effects
            if (NoiseSuppressor.isAvailable() && enableNS) {
                noiseSuppressor = NoiseSuppressor.create(audioRecord!!.audioSessionId)
                noiseSuppressor?.enabled = true
            }
            if (AutomaticGainControl.isAvailable() && enableAGC) {
                agc = AutomaticGainControl.create(audioRecord!!.audioSessionId)
                agc?.enabled = true
            }

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(audioFormat)
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelConfigOut)
                        .build()
                )
                .setBufferSizeInBytes(trackBufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioRecord?.startRecording()
            audioTrack?.play()

            recordJob = CoroutineScope(Dispatchers.Default).launch {
                val buffer = ShortArray(bufferSize / 2) // 16-bit = 2 bytes per sample
                while (isActive && isRunning) {
                    val readResult = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (readResult > 0) {
                        // Apply digital gain
                        if (gainFactor != 1.0f) {
                            for (i in 0 until readResult) {
                                // Simple clamping to avoid overflow wrapping
                                var sample = (buffer[i] * gainFactor).toInt()
                                if (sample > Short.MAX_VALUE) sample = Short.MAX_VALUE.toInt()
                                if (sample < Short.MIN_VALUE) sample = Short.MIN_VALUE.toInt()
                                buffer[i] = sample.toShort()
                            }
                        }
                        
                        // Write to local output if not muted
                        if (!muteLocal) {
                            audioTrack?.write(buffer, 0, readResult)
                        }

                        // Write to OutputStream (Bluetooth) if available
                        outputStream?.let { stream ->
                            try {
                                val bytes = ByteArray(readResult * 2)
                                ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().put(buffer, 0, readResult)
                                stream.write(bytes)
                            } catch (e: Exception) {
                                Log.e("AudioEngine", "Stream write failed", e)
                                // Optional: close stream on error?
                            }
                        }
                    }
                }
            }

        } catch (e: Exception) {
            Log.e("AudioEngine", "Error starting engine", e)
            stop()
        }
    }

    fun stop() {
        isRunning = false
        recordJob?.cancel()
        
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) { e.printStackTrace() }
        
        try {
            audioTrack?.stop()
            audioTrack?.release()
        } catch (e: Exception) { e.printStackTrace() }
        
        try {
            noiseSuppressor?.release()
            agc?.release()
        } catch (e: Exception) { e.printStackTrace() }

        audioRecord = null
        audioTrack = null
        noiseSuppressor = null
        agc = null
    }
}
