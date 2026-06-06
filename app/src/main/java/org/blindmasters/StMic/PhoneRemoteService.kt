package org.blindmasters.StMic

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothSocket
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONException
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.IOException
import java.io.InputStreamReader
import java.io.OutputStreamWriter

class PhoneRemoteService : Service() {

    private val binder = LocalBinder()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val phoneController by lazy { PhoneController(this) }
    private var activeSocket: BluetoothSocket? = null
    private var commandSessionJob: Job? = null
    private val telephonyManager by lazy { getSystemService(TelephonyManager::class.java) }

    private val bluetoothServer = BluetoothServer(
        serviceName = PhoneRemoteConfig.SERVICE_NAME,
        uuidString = PhoneRemoteConfig.SERVICE_UUID,
    ) { socket ->
        scope.launch {
            attachClient(socket)
        }
    }

    private val telephonyCallback = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
        override fun onCallStateChanged(state: Int) {
            PhoneRemoteStore.update { current ->
                current.copy(telephonyState = telephonyStateLabel(state))
            }
        }
    }

    inner class LocalBinder : Binder() {
        fun getService(): PhoneRemoteService = this@PhoneRemoteService
    }

    override fun onBind(intent: Intent): IBinder {
        return binder
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        phoneController.refreshRoleState()
        telephonyManager.registerTelephonyCallback(mainExecutor, telephonyCallback)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_REMOTE -> startRemoteServer()
            ACTION_STOP_REMOTE -> stopRemoteServer(removeNotification = true)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        commandSessionJob?.cancel()
        closeActiveSocket()
        bluetoothServer.stop()
        telephonyManager.unregisterTelephonyCallback(telephonyCallback)
        scope.cancel()
        super.onDestroy()
    }

    fun refreshRoleState() {
        phoneController.refreshRoleState()
    }

    fun dial(number: String, speakerphone: Boolean = false): Result<String> {
        refreshRoleState()
        return phoneController.dial(number, speakerphone)
    }

    fun sendSms(number: String, message: String): Result<String> {
        return phoneController.sendSms(number, message)
    }

    fun answerCall(): Result<String> {
        refreshRoleState()
        return phoneController.answerCall()
    }

    fun hangUpCall(): Result<String> {
        refreshRoleState()
        return phoneController.hangUpCall()
    }

    fun setMuted(muted: Boolean): Result<String> {
        refreshRoleState()
        return phoneController.setMuted(muted)
    }

    fun setSpeakerphone(enabled: Boolean): Result<String> {
        refreshRoleState()
        return phoneController.setSpeakerphone(enabled)
    }

    fun setAudioRoute(route: String): Result<String> {
        refreshRoleState()
        return phoneController.setAudioRoute(route)
    }

    private fun startRemoteServer() {
        startRemoteForeground()
        bluetoothServer.start()
        PhoneRemoteStore.update { current ->
            current.copy(
                serverRunning = bluetoothServer.isRunning,
                clientConnected = current.clientConnected && bluetoothServer.isRunning,
                lastError = if (bluetoothServer.isRunning) null else "Bluetooth remote server failed to start",
            )
        }
    }

    private fun stopRemoteServer(removeNotification: Boolean) {
        bluetoothServer.stop()
        commandSessionJob?.cancel()
        closeActiveSocket()
        PhoneRemoteStore.update { current ->
            current.copy(
                serverRunning = false,
                clientConnected = false,
            )
        }
        if (removeNotification) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun startRemoteForeground() {
        val stopIntent = Intent(this, PhoneRemoteService::class.java).apply {
            action = ACTION_STOP_REMOTE
        }
        val openIntent = Intent(this, MainActivity::class.java)
        val stopPendingIntent = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val openPendingIntent = PendingIntent.getActivity(
            this,
            2,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Phone Remote Active")
            .setContentText("Bluetooth phone control is listening for a paired client")
            .setSmallIcon(android.R.drawable.stat_sys_phone_call)
            .setContentIntent(openPendingIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPendingIntent)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Phone Remote",
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    @SuppressLint("MissingPermission")
    private fun attachClient(socket: BluetoothSocket) {
        commandSessionJob?.cancel()
        closeActiveSocket()
        activeSocket = socket
        PhoneRemoteStore.update { current ->
            current.copy(
                clientConnected = true,
                lastError = null,
            )
        }
        commandSessionJob = scope.launch {
            try {
                serveClient(socket)
            } finally {
                closeActiveSocket()
                PhoneRemoteStore.update { current ->
                    current.copy(clientConnected = false)
                }
            }
        }
    }

    private suspend fun serveClient(socket: BluetoothSocket) {
        val reader = BufferedReader(InputStreamReader(socket.inputStream))
        val writer = BufferedWriter(OutputStreamWriter(socket.outputStream))

        writeJson(
            writer,
            JSONObject()
                .put("type", "hello")
                .put("service", PhoneRemoteConfig.SERVICE_NAME)
                .put("uuid", PhoneRemoteConfig.SERVICE_UUID),
        )
        writeJson(writer, buildStatusJson())

        while (true) {
            val line = reader.readLine() ?: break
            val response = try {
                handleCommand(line)
            } catch (e: Exception) {
                failureResponse(null, e.message ?: "Command failed")
            }
            writeJson(writer, response)
        }
    }

    private fun handleCommand(line: String): JSONObject {
        val request = try {
            JSONObject(line)
        } catch (e: JSONException) {
            return failureResponse(null, "Invalid JSON request")
        }
        val action = request.optString("action").trim().lowercase()
        val requestId = request.optString("id").ifBlank { null }
        return when (action) {
            "status" -> buildStatusJson(requestId)
            "dial" -> resultResponse(
                requestId,
                dial(request.optString("number"), request.optBoolean("speakerphone", false)),
            )
            "send_sms", "sms" -> resultResponse(
                requestId,
                sendSms(request.optString("number"), request.optString("message")),
            )
            "answer" -> resultResponse(requestId, answerCall())
            "hang_up", "end_call", "disconnect" -> resultResponse(requestId, hangUpCall())
            "mute" -> {
                val enabled = if (request.has("enabled")) {
                    request.optBoolean("enabled")
                } else {
                    !PhoneRemoteStore.state.value.isMuted
                }
                resultResponse(requestId, setMuted(enabled))
            }
            "speaker" -> {
                val enabled = if (request.has("enabled")) {
                    request.optBoolean("enabled")
                } else {
                    PhoneRemoteStore.state.value.audioRoute != "SPEAKER"
                }
                resultResponse(requestId, setSpeakerphone(enabled))
            }
            "set_route", "route" -> resultResponse(
                requestId,
                setAudioRoute(request.optString("route")),
            )
            else -> failureResponse(requestId, "Unsupported action: $action")
        }
    }

    private fun resultResponse(requestId: String?, result: Result<String>): JSONObject {
        val error = result.exceptionOrNull()
        return if (error == null) {
            JSONObject()
                .put("id", requestId)
                .put("ok", true)
                .put("message", result.getOrNull())
                .put("status", buildStatusJson().getJSONObject("status"))
        } else {
            failureResponse(requestId, error.message ?: "Command failed")
        }
    }

    private fun failureResponse(requestId: String?, error: String): JSONObject {
        PhoneRemoteStore.update { current ->
            current.copy(lastError = error)
        }
        return JSONObject()
            .put("id", requestId)
            .put("ok", false)
            .put("error", error)
            .put("status", buildStatusJson().getJSONObject("status"))
    }

    private fun buildStatusJson(requestId: String? = null): JSONObject {
        val state = PhoneRemoteStore.state.value
        return JSONObject()
            .put("id", requestId)
            .put("ok", true)
            .put("type", "status")
            .put(
                "status",
                JSONObject()
                    .put("serverRunning", state.serverRunning)
                    .put("clientConnected", state.clientConnected)
                    .put("serviceName", state.bluetoothServiceName)
                    .put("serviceUuid", state.bluetoothServiceUuid)
                    .put("telephonyState", state.telephonyState)
                    .put("callState", state.callState)
                    .put("primaryNumber", state.primaryNumber)
                    .put("isDefaultDialer", state.isDefaultDialer)
                    .put("callControlAvailable", state.callControlAvailable)
                    .put("canAnswer", state.canAnswer)
                    .put("canHangUp", state.canHangUp)
                    .put("isMuted", state.isMuted)
                    .put("audioRoute", state.audioRoute)
                    .put("availableAudioRoutes", JSONArray(state.availableAudioRoutes))
                    .put("lastDialedNumber", state.lastDialedNumber)
                    .put("lastSmsTarget", state.lastSmsTarget)
                    .put("lastSmsPreview", state.lastSmsPreview)
                    .put("lastError", state.lastError),
            )
    }

    private fun writeJson(writer: BufferedWriter, json: JSONObject) {
        writer.write(json.toString())
        writer.newLine()
        writer.flush()
    }

    private fun closeActiveSocket() {
        try {
            activeSocket?.close()
        } catch (e: IOException) {
            Log.w("PhoneRemoteService", "Failed to close active Bluetooth socket", e)
        }
        activeSocket = null
    }

    private fun telephonyStateLabel(state: Int): String {
        return when (state) {
            TelephonyManager.CALL_STATE_IDLE -> "IDLE"
            TelephonyManager.CALL_STATE_RINGING -> "RINGING"
            TelephonyManager.CALL_STATE_OFFHOOK -> "OFFHOOK"
            else -> "UNKNOWN"
        }
    }

    companion object {
        const val ACTION_START_REMOTE = "org.blindmasters.StMic.action.START_PHONE_REMOTE"
        const val ACTION_STOP_REMOTE = "org.blindmasters.StMic.action.STOP_PHONE_REMOTE"
        private const val CHANNEL_ID = "PhoneRemoteChannel"
        private const val NOTIFICATION_ID = 41
    }
}
