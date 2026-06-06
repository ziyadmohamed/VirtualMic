package org.blindmasters.StMic

import android.Manifest
import android.app.role.RoleManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import org.blindmasters.StMic.ui.theme.StMicTheme

class MainActivity : ComponentActivity() {

    private var micService: MicService? = null
    private var phoneRemoteService: PhoneRemoteService? = null
    private var isMicBound = false
    private var isPhoneRemoteBound = false
    private val dialerPrefill = mutableStateOf("")

    private val micConnection = object : ServiceConnection {
        override fun onServiceConnected(className: ComponentName, service: IBinder) {
            val binder = service as MicService.LocalBinder
            micService = binder.getService()
            isMicBound = true
        }

        override fun onServiceDisconnected(arg0: ComponentName) {
            isMicBound = false
            micService = null
        }
    }

    private val phoneRemoteConnection = object : ServiceConnection {
        override fun onServiceConnected(className: ComponentName, service: IBinder) {
            val binder = service as PhoneRemoteService.LocalBinder
            phoneRemoteService = binder.getService()
            phoneRemoteService?.refreshRoleState()
            isPhoneRemoteBound = true
        }

        override fun onServiceDisconnected(arg0: ComponentName) {
            isPhoneRemoteBound = false
            phoneRemoteService = null
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { }

    private val dialerRoleLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) {
        updateDialerRoleState()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        captureDialIntent(intent)
        requestRuntimePermissions()

        setContent {
            StMicTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    MainScreen()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        captureDialIntent(intent)
    }

    override fun onStart() {
        super.onStart()
        Intent(this, MicService::class.java).also { intent ->
            bindService(intent, micConnection, Context.BIND_AUTO_CREATE)
        }
        Intent(this, PhoneRemoteService::class.java).also { intent ->
            bindService(intent, phoneRemoteConnection, Context.BIND_AUTO_CREATE)
        }
        updateDialerRoleState()
    }

    override fun onStop() {
        if (isMicBound) {
            unbindService(micConnection)
            isMicBound = false
        }
        if (isPhoneRemoteBound) {
            unbindService(phoneRemoteConnection)
            isPhoneRemoteBound = false
        }
        super.onStop()
    }

    private fun captureDialIntent(intent: Intent?) {
        dialerPrefill.value = intent?.data?.schemeSpecificPart.orEmpty()
    }

    private fun requestRuntimePermissions() {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CALL_PHONE,
            Manifest.permission.SEND_SMS,
            Manifest.permission.READ_PHONE_STATE,
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions += Manifest.permission.POST_NOTIFICATIONS
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions += Manifest.permission.BLUETOOTH_CONNECT
            permissions += Manifest.permission.BLUETOOTH_SCAN
            permissions += Manifest.permission.BLUETOOTH_ADVERTISE
        }

        permissionLauncher.launch(permissions.toTypedArray())
    }

    private fun requestDialerRole() {
        val roleManager = getSystemService(RoleManager::class.java) ?: return
        if (roleManager.isRoleHeld(RoleManager.ROLE_DIALER)) {
            updateDialerRoleState()
            return
        }
        dialerRoleLauncher.launch(roleManager.createRequestRoleIntent(RoleManager.ROLE_DIALER))
    }

    private fun updateDialerRoleState() {
        val roleManager = getSystemService(RoleManager::class.java)
        val isHeld = roleManager?.isRoleHeld(RoleManager.ROLE_DIALER) == true
        PhoneRemoteStore.update { current ->
            current.copy(isDefaultDialer = isHeld)
        }
        phoneRemoteService?.refreshRoleState()
    }

    private fun startMic(
        enableBluetooth: Boolean,
        gain: Float,
        micSource: Int,
        useStereo: Boolean,
        enableAGC: Boolean,
        enableNS: Boolean,
    ) {
        val intent = Intent(this, MicService::class.java).apply {
            putExtra(MicService.EXTRA_ENABLE_BT, enableBluetooth)
            putExtra(MicService.EXTRA_MUTE_LOCAL, enableBluetooth)
            putExtra(MicService.EXTRA_GAIN, gain)
            putExtra(MicService.EXTRA_MIC_SOURCE, micSource)
            putExtra(MicService.EXTRA_USE_STEREO, useStereo)
            putExtra(MicService.EXTRA_ENABLE_AGC, enableAGC)
            putExtra(MicService.EXTRA_ENABLE_NS, enableNS)
        }
        startForegroundService(intent)
    }

    private fun stopMic() {
        val intent = Intent(this, MicService::class.java).apply {
            action = MicService.ACTION_STOP
        }
        startService(intent)
    }

    private fun startPhoneRemote() {
        val intent = Intent(this, PhoneRemoteService::class.java).apply {
            action = PhoneRemoteService.ACTION_START_REMOTE
        }
        startForegroundService(intent)
    }

    private fun stopPhoneRemote() {
        val intent = Intent(this, PhoneRemoteService::class.java).apply {
            action = PhoneRemoteService.ACTION_STOP_REMOTE
        }
        startService(intent)
    }

    @Composable
    private fun MainScreen() {
        var isRunning by remember { mutableStateOf(false) }
        var gain by remember { mutableFloatStateOf(1.0f) }
        var micSource by remember { mutableIntStateOf(MediaRecorder.AudioSource.MIC) }
        var useStereo by remember { mutableStateOf(false) }
        var enableAGC by remember { mutableStateOf(false) }
        var enableNS by remember { mutableStateOf(false) }
        var transportMode by remember { mutableStateOf(TransportMode.SPEAKER) }
        var btStatus by remember { mutableStateOf(false) }
        var callNumber by rememberSaveable { mutableStateOf("") }
        var smsNumber by rememberSaveable { mutableStateOf("") }
        var smsMessage by rememberSaveable { mutableStateOf("") }
        val phoneState by PhoneRemoteStore.state.collectAsState()
        val prefilledNumber by dialerPrefill

        LaunchedEffect(prefilledNumber) {
            if (prefilledNumber.isNotBlank()) {
                callNumber = prefilledNumber
                if (smsNumber.isBlank()) {
                    smsNumber = prefilledNumber
                }
            }
        }

        LaunchedEffect(isMicBound, micService) {
            while (isActive) {
                val service = micService
                if (isMicBound && service != null) {
                    isRunning = service.audioEngine.isRunning
                    btStatus = service.isBtRunning
                }
                delay(500)
            }
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("StMic Remote", style = MaterialTheme.typography.headlineMedium)
            PhoneRemoteCard(
                phoneState = phoneState,
                controlsEnabled = isPhoneRemoteBound && phoneRemoteService != null,
                callNumber = callNumber,
                onCallNumberChange = { callNumber = it },
                smsNumber = smsNumber,
                onSmsNumberChange = { smsNumber = it },
                smsMessage = smsMessage,
                onSmsMessageChange = { smsMessage = it },
            )
            MicCard(
                isRunning = isRunning,
                gain = gain,
                onGainChange = {
                    gain = it
                    micService?.audioEngine?.gainFactor = it
                },
                micSource = micSource,
                onMicSourceChange = { micSource = it },
                useStereo = useStereo,
                onUseStereoChange = { useStereo = it },
                enableAGC = enableAGC,
                onEnableAGCChange = { enableAGC = it },
                enableNS = enableNS,
                onEnableNSChange = { enableNS = it },
                transportMode = transportMode,
                onTransportModeChange = { transportMode = it },
                btStatus = btStatus,
                onToggleMic = {
                    if (isRunning) {
                        stopMic()
                    } else {
                        micService?.audioEngine?.let { engine ->
                            engine.gainFactor = gain
                            engine.selectedSource = micSource
                            engine.useStereo = useStereo
                            engine.enableAGC = enableAGC
                            engine.enableNS = enableNS
                        }
                        startMic(
                            enableBluetooth = transportMode == TransportMode.BLUETOOTH,
                            gain = gain,
                            micSource = micSource,
                            useStereo = useStereo,
                            enableAGC = enableAGC,
                            enableNS = enableNS,
                        )
                    }
                },
            )
        }
    }

    @Composable
    private fun PhoneRemoteCard(
        phoneState: PhoneRemoteState,
        controlsEnabled: Boolean,
        callNumber: String,
        onCallNumberChange: (String) -> Unit,
        smsNumber: String,
        onSmsNumberChange: (String) -> Unit,
        smsMessage: String,
        onSmsMessageChange: (String) -> Unit,
    ) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Phone Remote", style = MaterialTheme.typography.headlineSmall)
                Text(
                    text = "${phoneState.bluetoothServiceName} (${phoneState.bluetoothServiceUuid})",
                    style = MaterialTheme.typography.bodySmall,
                )
                StatusLine("Dialer role", if (phoneState.isDefaultDialer) "Granted" else "Not granted")
                StatusLine(
                    "Bluetooth remote",
                    when {
                        phoneState.clientConnected -> "Client connected"
                        phoneState.serverRunning -> "Waiting for client"
                        else -> "Stopped"
                    },
                )
                StatusLine("Call state", phoneState.callState)
                StatusLine("Network state", phoneState.telephonyState)
                if (phoneState.primaryNumber.isNotBlank()) {
                    StatusLine("Current number", phoneState.primaryNumber)
                }
                StatusLine("Route", phoneState.audioRoute)
                if (phoneState.availableAudioRoutes.isNotEmpty()) {
                    Text(
                        text = "Available routes: ${phoneState.availableAudioRoutes.joinToString()}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (!phoneState.lastError.isNullOrBlank()) {
                    Text(
                        text = phoneState.lastError.orEmpty(),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { requestDialerRole() },
                        modifier = Modifier.weight(1f),
                        enabled = !phoneState.isDefaultDialer,
                    ) {
                        Text(if (phoneState.isDefaultDialer) "Dialer Ready" else "Request Dialer Role")
                    }
                    Button(
                        onClick = {
                            if (phoneState.serverRunning) {
                                stopPhoneRemote()
                            } else {
                                startPhoneRemote()
                            }
                        },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(if (phoneState.serverRunning) "Stop Remote" else "Start Remote")
                    }
                }

                OutlinedTextField(
                    value = callNumber,
                    onValueChange = onCallNumberChange,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Phone number") },
                    singleLine = true,
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { phoneRemoteService?.dial(callNumber) },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled,
                    ) {
                        Text("Call")
                    }
                    Button(
                        onClick = { phoneRemoteService?.dial(callNumber, speakerphone = true) },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled,
                    ) {
                        Text("Call Speaker")
                    }
                }

                OutlinedTextField(
                    value = smsNumber,
                    onValueChange = onSmsNumberChange,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("SMS number") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = smsMessage,
                    onValueChange = onSmsMessageChange,
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("SMS message") },
                    minLines = 3,
                )

                Button(
                    onClick = {
                        phoneRemoteService?.sendSms(
                            if (smsNumber.isBlank()) callNumber else smsNumber,
                            smsMessage,
                        )
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = controlsEnabled,
                ) {
                    Text("Send SMS")
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { phoneRemoteService?.answerCall() },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled && phoneState.canAnswer,
                    ) {
                        Text("Answer")
                    }
                    Button(
                        onClick = { phoneRemoteService?.hangUpCall() },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled && phoneState.canHangUp,
                    ) {
                        Text("Hang Up")
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { phoneRemoteService?.setMuted(!phoneState.isMuted) },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled && phoneState.callControlAvailable,
                    ) {
                        Text(if (phoneState.isMuted) "Unmute" else "Mute")
                    }
                    Button(
                        onClick = {
                            phoneRemoteService?.setSpeakerphone(phoneState.audioRoute != "SPEAKER")
                        },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled && phoneState.callControlAvailable,
                    ) {
                        Text(if (phoneState.audioRoute == "SPEAKER") "Use Earpiece" else "Use Speaker")
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { phoneRemoteService?.setAudioRoute("EARPIECE") },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled &&
                            phoneState.callControlAvailable &&
                            "EARPIECE" in phoneState.availableAudioRoutes,
                    ) {
                        Text("Earpiece")
                    }
                    Button(
                        onClick = { phoneRemoteService?.setAudioRoute("WIRED_HEADSET") },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled &&
                            phoneState.callControlAvailable &&
                            "WIRED_HEADSET" in phoneState.availableAudioRoutes,
                    ) {
                        Text("Wired")
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { phoneRemoteService?.setAudioRoute("BLUETOOTH") },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled &&
                            phoneState.callControlAvailable &&
                            "BLUETOOTH" in phoneState.availableAudioRoutes,
                    ) {
                        Text("Bluetooth")
                    }
                    Button(
                        onClick = { phoneRemoteService?.setAudioRoute("SPEAKER") },
                        modifier = Modifier.weight(1f),
                        enabled = controlsEnabled &&
                            phoneState.callControlAvailable &&
                            "SPEAKER" in phoneState.availableAudioRoutes,
                    ) {
                        Text("Speaker")
                    }
                }

                Text(
                    text = "Supported with public Android APIs: dialing, SMS, answer/end, mute, and supported in-call route switching. Arbitrary audio injection into carrier calls is not supported here.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }

    @Composable
    private fun MicCard(
        isRunning: Boolean,
        gain: Float,
        onGainChange: (Float) -> Unit,
        micSource: Int,
        onMicSourceChange: (Int) -> Unit,
        useStereo: Boolean,
        onUseStereoChange: (Boolean) -> Unit,
        enableAGC: Boolean,
        onEnableAGCChange: (Boolean) -> Unit,
        enableNS: Boolean,
        onEnableNSChange: (Boolean) -> Unit,
        transportMode: TransportMode,
        onTransportModeChange: (TransportMode) -> Unit,
        btStatus: Boolean,
        onToggleMic: () -> Unit,
    ) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Mic Stream", style = MaterialTheme.typography.headlineSmall)
                Button(
                    onClick = onToggleMic,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (isRunning) "STOP MIC" else "START MIC")
                }

                Text("Gain: ${String.format("%.1f", gain)}x")
                Slider(
                    value = gain,
                    onValueChange = onGainChange,
                    valueRange = 0f..10f,
                )

                Text("Transport Mode:")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = transportMode == TransportMode.SPEAKER,
                        onClick = { onTransportModeChange(TransportMode.SPEAKER) },
                    )
                    Text("Speaker (Local)")
                    Spacer(modifier = Modifier.width(16.dp))
                    RadioButton(
                        selected = transportMode == TransportMode.BLUETOOTH,
                        onClick = { onTransportModeChange(TransportMode.BLUETOOTH) },
                    )
                    Text("Bluetooth (PC)")
                }

                if (isRunning && transportMode == TransportMode.BLUETOOTH) {
                    Text(
                        text = if (btStatus) {
                            "Bluetooth server is ready. Start the Windows receiver and connect now."
                        } else {
                            "Bluetooth transport is stopped."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = useStereo,
                        onCheckedChange = onUseStereoChange,
                    )
                    Text("Stereo (Requires Restart)")
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = enableAGC,
                        onCheckedChange = onEnableAGCChange,
                    )
                    Text("Auto Gain Control")
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = enableNS,
                        onCheckedChange = onEnableNSChange,
                    )
                    Text("Noise Suppression")
                }

                Text("Microphone Source:")
                SourceOption("Default", MediaRecorder.AudioSource.MIC, micSource, onMicSourceChange)
                SourceOption("Camcorder", MediaRecorder.AudioSource.CAMCORDER, micSource, onMicSourceChange)
                SourceOption("Unprocessed", MediaRecorder.AudioSource.UNPROCESSED, micSource, onMicSourceChange)
                SourceOption("Voice Rec", MediaRecorder.AudioSource.VOICE_RECOGNITION, micSource, onMicSourceChange)

                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Bluetooth mic mode still uses the existing low-latency audio pipeline for the Windows receiver.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }

    @Composable
    private fun StatusLine(label: String, value: String) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(value, style = MaterialTheme.typography.bodyMedium, color = Color.Gray)
        }
    }

    @Composable
    private fun SourceOption(label: String, value: Int, current: Int, onSelect: (Int) -> Unit) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            RadioButton(
                selected = value == current,
                onClick = { onSelect(value) },
            )
            Text(label)
        }
    }

    enum class TransportMode {
        SPEAKER,
        BLUETOOTH,
    }
}
