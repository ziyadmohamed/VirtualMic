package org.blindmasters.StMic

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaCodec
import android.media.MediaCodecList
import android.media.MediaFormat
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

class AudioEngine {

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var agc: AutomaticGainControl? = null
    private var opusEncoder: MediaCodec? = null
    private var opusFramesSubmitted: Long = 0

    @Volatile
    private var outputStream: OutputStream? = null

    private var recordJob: Job? = null
    private var activeSampleRate = 48000
    private var activeChannelCount = 1
    private var activeTransportFormatCode: Short = TRANSPORT_PCM16
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
        this.outputStream = stream?.let { BufferedOutputStream(it, 1024) }
    }

    fun currentSampleRate(): Int {
        return if (isRunning) activeSampleRate else plannedSampleRate()
    }

    fun currentChannelCount(): Int {
        return if (isRunning) activeChannelCount else plannedChannelCount()
    }

    fun currentTransportFormatCode(): Short {
        return if (isRunning) activeTransportFormatCode else plannedTransportFormatCode()
    }

    private fun plannedSampleRate(): Int {
        return if (bluetoothOptimized) 48000 else 48000
    }

    private fun plannedChannelCount(): Int {
        return if (useStereo) 2 else 1
    }

    private fun plannedTransportFormatCode(): Short {
        return if (bluetoothOptimized) TRANSPORT_OPUS else TRANSPORT_PCM16
    }

    private fun resolveOpusBitrate(channelCount: Int): Int {
        return if (channelCount == 2) 128_000 else 64_000
    }

    private fun findOpusEncoderName(sampleRate: Int, channelCount: Int): String? {
        val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, sampleRate, channelCount).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, resolveOpusBitrate(channelCount))
        }
        return MediaCodecList(MediaCodecList.ALL_CODECS).findEncoderForFormat(format)
    }

    private fun createOpusEncoder(sampleRate: Int, channelCount: Int): MediaCodec {
        val codecName = findOpusEncoderName(sampleRate, channelCount)
            ?: throw IllegalStateException("No Opus encoder available on this device")
        val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, sampleRate, channelCount).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, resolveOpusBitrate(channelCount))
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, sampleRate * channelCount * 2 / 10)
        }
        val codec = MediaCodec.createByCodecName(codecName)
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        codec.start()
        Log.d(
            "AudioEngine",
            "Using Opus encoder $codecName at ${sampleRate}Hz, ${channelCount}ch, ${resolveOpusBitrate(channelCount)}bps"
        )
        return codec
    }

    private fun shortsToLittleEndianBytes(samples: ShortArray, count: Int): ByteArray {
        val bytes = ByteArray(count * 2)
        ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().put(samples, 0, count)
        return bytes
    }

    private fun queueOpusInput(codec: MediaCodec, bytes: ByteArray, byteCount: Int, sampleRate: Int, channelCount: Int) {
        var offset = 0
        while (offset < byteCount) {
            val inputIndex = codec.dequeueInputBuffer(10_000)
            if (inputIndex < 0) {
                continue
            }
            val inputBuffer = codec.getInputBuffer(inputIndex)
                ?: throw IllegalStateException("Opus encoder input buffer is null")
            inputBuffer.clear()
            val toWrite = minOf(inputBuffer.remaining(), byteCount - offset)
            inputBuffer.put(bytes, offset, toWrite)
            val frames = toWrite / (channelCount * 2)
            val ptsUs = (opusFramesSubmitted * 1_000_000L) / sampleRate
            codec.queueInputBuffer(inputIndex, 0, toWrite, ptsUs, 0)
            opusFramesSubmitted += frames.toLong()
            offset += toWrite
        }
    }

    private fun drainOpusEncoder(codec: MediaCodec, stream: OutputStream) {
        val bufferInfo = MediaCodec.BufferInfo()
        while (true) {
            val outputIndex = codec.dequeueOutputBuffer(bufferInfo, 0)
            when {
                outputIndex == MediaCodec.INFO_TRY_AGAIN_LATER -> return
                outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    Log.d("AudioEngine", "Opus output format changed: ${codec.outputFormat}")
                }
                outputIndex >= 0 -> {
                    val outputBuffer = codec.getOutputBuffer(outputIndex)
                    if (outputBuffer != null && bufferInfo.size > 0 && (bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                        val packet = ByteArray(bufferInfo.size)
                        outputBuffer.position(bufferInfo.offset)
                        outputBuffer.limit(bufferInfo.offset + bufferInfo.size)
                        outputBuffer.get(packet)
                        stream.write(ByteBuffer.allocate(OPUS_PACKET_PREFIX_BYTES).order(ByteOrder.LITTLE_ENDIAN).putInt(packet.size).array())
                        stream.write(packet)
                        stream.flush()
                    }
                    codec.releaseOutputBuffer(outputIndex, false)
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRunning) return
        isRunning = true

        var sampleRate = plannedSampleRate()
        val channelCount = plannedChannelCount()
        var transportFormatCode = plannedTransportFormatCode()

        val wantsOpus = bluetoothOptimized
        if (wantsOpus) {
            val encoderName = findOpusEncoderName(sampleRate, channelCount)
            if (encoderName == null) {
                transportFormatCode = TRANSPORT_PCM16
                sampleRate = 24000
                Log.w("AudioEngine", "Opus encoder unavailable, falling back to raw PCM16 at ${sampleRate}Hz")
            } else {
                Log.d("AudioEngine", "Opus encoder discovered: $encoderName")
            }
        }

        activeSampleRate = sampleRate
        activeChannelCount = channelCount
        activeTransportFormatCode = transportFormatCode
        opusFramesSubmitted = 0

        val channelConfigIn = if (channelCount == 2) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
        val channelConfigOut = if (channelCount == 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        val bytesPerFrame = channelCount * 2

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

            if (transportFormatCode == TRANSPORT_OPUS) {
                opusEncoder = createOpusEncoder(sampleRate, channelCount)
            }

            audioRecord?.startRecording()
            audioTrack?.play()

            recordJob = CoroutineScope(Dispatchers.IO).launch {
                val buffer = ShortArray(bufferSize / 2)
                while (isActive && isRunning) {
                    val readResult = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (readResult <= 0) {
                        continue
                    }

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
                            val bytes = shortsToLittleEndianBytes(buffer, readResult)
                            if (transportFormatCode == TRANSPORT_OPUS) {
                                val codec = opusEncoder
                                    ?: throw IllegalStateException("Opus transport selected but encoder is null")
                                queueOpusInput(codec, bytes, bytes.size, sampleRate, channelCount)
                                drainOpusEncoder(codec, stream)
                            } else {
                                stream.write(bytes)
                            }
                        } catch (e: Exception) {
                            Log.e("AudioEngine", "Stream write failed", e)
                            outputStream = null
                            onStreamError?.invoke(e)
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
            opusEncoder?.stop()
            opusEncoder?.release()
        } catch (e: Exception) {
            e.printStackTrace()
        }

        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            e.printStackTrace()
        }

        try {
            audioTrack?.stop()
            audioTrack?.release()
        } catch (e: Exception) {
            e.printStackTrace()
        }

        try {
            noiseSuppressor?.release()
            agc?.release()
        } catch (e: Exception) {
            e.printStackTrace()
        }

        audioRecord = null
        audioTrack = null
        noiseSuppressor = null
        agc = null
        opusEncoder = null
        opusFramesSubmitted = 0
    }

    companion object {
        const val TRANSPORT_PCM16: Short = 1
        const val TRANSPORT_OPUS: Short = 10
        private const val OPUS_PACKET_PREFIX_BYTES = 4
    }
}
