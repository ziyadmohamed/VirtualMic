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
import java.io.BufferedOutputStream
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
    
    @Volatile
    private var outputStream: OutputStream? = null

    private var recordJob: Job? = null
    var isRunning = false
        private set
    var onStreamError: ((Exception) -> Unit)? = null

    // Configuration
    var gainFactor: Float = 1.0f
    var useStereo: Boolean = false
    var enableNS: Boolean = false
    var enableAGC: Boolean = false
    var selectedSource: Int = MediaRecorder.AudioSource.MIC
    var muteLocal: Boolean = false
    var bluetoothOptimized: Boolean = false
    
    fun setStream(stream: OutputStream?) {
        this.outputStream = stream?.let { BufferedOutputStream(it, 8192) }
    }

    fun currentSampleRate(): Int {
        return if (bluetoothOptimized) {
            24000
        } else {
            48000
        }
    }

    fun currentChannelCount(): Int {
        return if (bluetoothOptimized) {
            if (useStereo) 2 else 1
        } else if (useStereo) {
            2
        } else {
            1
        }
    }

    fun currentTransportFormatCode(): Short {
        return if (bluetoothOptimized && useStereo) 3 else 1
    }

    private fun currentAudioEncoding(): Int {
        return if (bluetoothOptimized && useStereo) {
            AudioFormat.ENCODING_PCM_FLOAT
        } else {
            AudioFormat.ENCODING_PCM_16BIT
        }
    }

    private fun currentBytesPerSample(): Int {
        return if (currentAudioEncoding() == AudioFormat.ENCODING_PCM_FLOAT) 4 else 2
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRunning) return
        isRunning = true

        val sampleRate = currentSampleRate()
        val useMonoForTransport = bluetoothOptimized && !useStereo
        val channelConfigIn = if (!useMonoForTransport && useStereo) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
        val channelConfigOut = if (!useMonoForTransport && useStereo) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val audioFormat = currentAudioEncoding()
        val bytesPerFrame = currentChannelCount() * currentBytesPerSample()

        val minBufSize = AudioRecord.getMinBufferSize(sampleRate, channelConfigIn, audioFormat)
        val targetBufferBytes = sampleRate * bytesPerFrame / 100
        val bufferSize = max(minBufSize, targetBufferBytes)
        val trackBufferSize = if (!muteLocal) {
            AudioTrack.getMinBufferSize(sampleRate, channelConfigOut, audioFormat)
        } else {
            0
        }

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

            if (!muteLocal) {
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
            }

            audioRecord?.startRecording()
            audioTrack?.play()

            recordJob = CoroutineScope(Dispatchers.Default).launch {
                if (audioFormat == AudioFormat.ENCODING_PCM_FLOAT) {
                    val buffer = FloatArray(bufferSize / 4)
                    var bytes = ByteArray(bufferSize)
                    while (isActive && isRunning) {
                        val readResult = audioRecord?.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING) ?: -1
                        if (readResult > 0) {
                            if (gainFactor != 1.0f) {
                                for (i in 0 until readResult) {
                                    buffer[i] = min(1.0f, max(-1.0f, buffer[i] * gainFactor))
                                }
                            }

                            outputStream?.let { stream ->
                                try {
                                    val byteCount = readResult * 4
                                    if (bytes.size < byteCount) {
                                        bytes = ByteArray(byteCount)
                                    }
                                    ByteBuffer.wrap(bytes, 0, byteCount)
                                        .order(ByteOrder.LITTLE_ENDIAN)
                                        .asFloatBuffer()
                                        .put(buffer, 0, readResult)
                                    stream.write(bytes, 0, byteCount)
                                } catch (e: Exception) {
                                    Log.e("AudioEngine", "Stream write failed", e)
                                    outputStream = null
                                    onStreamError?.invoke(e)
                                }
                            }
                        }
                    }
                } else {
                    val buffer = ShortArray(bufferSize / 2)
                    while (isActive && isRunning) {
                        val readResult = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                        if (readResult > 0) {
                            if (gainFactor != 1.0f) {
                                for (i in 0 until readResult) {
                                    var sample = (buffer[i] * gainFactor).toInt()
                                    if (sample > Short.MAX_VALUE) sample = Short.MAX_VALUE.toInt()
                                    if (sample < Short.MIN_VALUE) sample = Short.MIN_VALUE.toInt()
                                    buffer[i] = sample.toShort()
                                }
                            }
                            
                            if (!muteLocal) {
                                audioTrack?.write(buffer, 0, readResult)
                            }

                            outputStream?.let { stream ->
                                try {
                                    val bytes = ByteArray(readResult * 2)
                                    ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().put(buffer, 0, readResult)
                                    stream.write(bytes)
                                } catch (e: Exception) {
                                    Log.e("AudioEngine", "Stream write failed", e)
                                    outputStream = null
                                    onStreamError?.invoke(e)
                                }
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
