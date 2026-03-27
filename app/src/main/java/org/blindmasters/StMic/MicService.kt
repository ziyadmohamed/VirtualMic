package org.blindmasters.StMic

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder

class MicService : Service() {

    private val binder = LocalBinder()
    val audioEngine = AudioEngine()
    private var activeSocket: BluetoothSocket? = null
    
    val isBtRunning: Boolean
        get() = bluetoothServer.isRunning

    private val bluetoothServer = BluetoothServer { socket ->
        closeActiveSocket()
        writeBluetoothHeader(socket)
        activeSocket = socket
        audioEngine.setStream(socket.outputStream)
    }
    
    inner class LocalBinder : Binder() {
        fun getService(): MicService = this@MicService
    }

    override fun onBind(intent: Intent): IBinder {
        return binder
    }

    override fun onCreate() {
        super.onCreate()
        audioEngine.onStreamError = { error ->
            Log.e("MicService", "Bluetooth stream disconnected", error)
            closeActiveSocket()
            audioEngine.setStream(null)
        }
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopStreaming()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }

        startForegroundService()
        
        val enableBt = intent?.getBooleanExtra(EXTRA_ENABLE_BT, false) ?: false
        val muteLocal = intent?.getBooleanExtra(EXTRA_MUTE_LOCAL, false) ?: false
        audioEngine.gainFactor = intent?.getFloatExtra(EXTRA_GAIN, audioEngine.gainFactor) ?: audioEngine.gainFactor
        audioEngine.selectedSource = intent?.getIntExtra(EXTRA_MIC_SOURCE, audioEngine.selectedSource) ?: audioEngine.selectedSource
        audioEngine.useStereo = intent?.getBooleanExtra(EXTRA_USE_STEREO, audioEngine.useStereo) ?: audioEngine.useStereo
        audioEngine.enableAGC = intent?.getBooleanExtra(EXTRA_ENABLE_AGC, audioEngine.enableAGC) ?: audioEngine.enableAGC
        audioEngine.enableNS = intent?.getBooleanExtra(EXTRA_ENABLE_NS, audioEngine.enableNS) ?: audioEngine.enableNS
        
        audioEngine.bluetoothOptimized = enableBt
        audioEngine.muteLocal = muteLocal
        Log.d(
            "MicService",
            "Starting mic: bt=$enableBt stereo=${audioEngine.useStereo} sampleRate=${audioEngine.currentSampleRate()} channels=${audioEngine.currentChannelCount()} source=${audioEngine.selectedSource} gain=${audioEngine.gainFactor}"
        )
        if (!audioEngine.isRunning) {
            audioEngine.start()
        }
        
        if (enableBt) {
            bluetoothServer.start()
        } else {
            bluetoothServer.stop()
            closeActiveSocket()
            audioEngine.setStream(null)
        }
        
        return START_STICKY
    }
    
    private fun startForegroundService() {
        val stopIntent = Intent(this, MicService::class.java).apply {
            action = ACTION_STOP
        }
        val pendingStopIntent = PendingIntent.getService(
            this, 0, stopIntent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("StMic Active")
            .setContentText("Microphone passthrough is running...")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .addAction(android.R.drawable.ic_media_pause, "Stop", pendingStopIntent)
            .setOngoing(true)
            .build()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(1, notification)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "Mic Service Channel",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(serviceChannel)
        }
    }

    override fun onDestroy() {
        stopStreaming()
        super.onDestroy()
    }

    private fun stopStreaming() {
        bluetoothServer.stop()
        closeActiveSocket()
        audioEngine.setStream(null)
        audioEngine.stop()
    }

    private fun closeActiveSocket() {
        try {
            activeSocket?.close()
        } catch (e: IOException) {
            e.printStackTrace()
        }
        activeSocket = null
    }

    private fun writeBluetoothHeader(socket: BluetoothSocket) {
        val sampleRate = audioEngine.currentSampleRate()
        val channels = audioEngine.currentChannelCount()
        val header = ByteBuffer.allocate(12)
            .order(ByteOrder.LITTLE_ENDIAN)
            .put(byteArrayOf(0x53, 0x54, 0x4D, 0x31))
            .putInt(sampleRate)
            .putShort(channels.toShort())
            .putShort(1)
            .array()
        socket.outputStream.write(header)
        socket.outputStream.flush()
        Log.d("MicService", "Sent Bluetooth header: ${sampleRate}Hz, ${channels}ch")
    }

    companion object {
        const val CHANNEL_ID = "MicServiceChannel"
        const val ACTION_STOP = "STOP_ACTION"
        const val EXTRA_ENABLE_BT = "ENABLE_BT"
        const val EXTRA_MUTE_LOCAL = "MUTE_LOCAL"
        const val EXTRA_GAIN = "GAIN"
        const val EXTRA_MIC_SOURCE = "MIC_SOURCE"
        const val EXTRA_USE_STEREO = "USE_STEREO"
        const val EXTRA_ENABLE_AGC = "ENABLE_AGC"
        const val EXTRA_ENABLE_NS = "ENABLE_NS"
    }
}
