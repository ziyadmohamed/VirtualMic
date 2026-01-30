package org.blindmasters.StMic

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class MicService : Service() {

    private val binder = LocalBinder()
    val audioEngine = AudioEngine()
    
    val isBtRunning: Boolean
        get() = bluetoothServer.isRunning

    private val bluetoothServer = BluetoothServer { socket ->
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
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            audioEngine.stop()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }

        startForegroundService()
        
        val enableBt = intent?.getBooleanExtra(EXTRA_ENABLE_BT, false) ?: false
        val muteLocal = intent?.getBooleanExtra(EXTRA_MUTE_LOCAL, false) ?: false
        
        audioEngine.muteLocal = muteLocal
        audioEngine.start()
        
        if (enableBt) {
            bluetoothServer.start()
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
        super.onDestroy()
        audioEngine.stop()
        bluetoothServer.stop()
    }

    companion object {
        const val CHANNEL_ID = "MicServiceChannel"
        const val ACTION_STOP = "STOP_ACTION"
        const val EXTRA_ENABLE_BT = "ENABLE_BT"
        const val EXTRA_MUTE_LOCAL = "MUTE_LOCAL"
    }
}
