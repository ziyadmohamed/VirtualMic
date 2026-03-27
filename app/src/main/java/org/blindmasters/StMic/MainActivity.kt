package org.blindmasters.StMic

import android.Manifest
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
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import org.blindmasters.StMic.ui.theme.StMicTheme

class MainActivity : ComponentActivity() {

    private var micService: MicService? = null
    private var isBound = false

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(className: ComponentName, service: IBinder) {
            val binder = service as MicService.LocalBinder
            micService = binder.getService()
            isBound = true
        }

        override fun onServiceDisconnected(arg0: ComponentName) {
            isBound = false
            micService = null
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestRuntimePermissions()

        setContent {
            StMicTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen()
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        Intent(this, MicService::class.java).also { intent ->
            bindService(intent, connection, Context.BIND_AUTO_CREATE)
        }
    }

    override fun onStop() {
        if (isBound) {
            unbindService(connection)
            isBound = false
        }
        super.onStop()
    }

    private fun requestRuntimePermissions() {
        val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)

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

    @Composable
    fun MainScreen() {
        var isRunning by remember { mutableStateOf(false) }
        var gain by remember { mutableFloatStateOf(1.0f) }
        var micSource by remember { mutableIntStateOf(MediaRecorder.AudioSource.MIC) }
        var useStereo by remember { mutableStateOf(false) }
        var enableAGC by remember { mutableStateOf(false) }
        var enableNS by remember { mutableStateOf(false) }
        var transportMode by remember { mutableStateOf(TransportMode.SPEAKER) }
        var btStatus by remember { mutableStateOf(false) }

        LaunchedEffect(isBound, micService) {
            while (isActive) {
                val service = micService
                if (isBound && service != null) {
                    isRunning = service.audioEngine.isRunning
                    btStatus = service.isBtRunning
                }
                delay(500)
            }
        }

        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text("StMic Controller", style = MaterialTheme.typography.headlineMedium)

            Button(
                onClick = {
                    if (isRunning) {
                        stopMic()
                    } else {
                        micService?.audioEngine?.let {
                            it.gainFactor = gain
                            it.selectedSource = micSource
                            it.useStereo = useStereo
                            it.enableAGC = enableAGC
                            it.enableNS = enableNS
                        }
                        startMic(transportMode == TransportMode.BLUETOOTH)
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (isRunning) "STOP MIC" else "START MIC")
            }

            Text("Gain: ${String.format("%.1f", gain)}x")
            Slider(
                value = gain,
                onValueChange = {
                    gain = it
                    micService?.audioEngine?.gainFactor = it
                },
                valueRange = 0f..10f
            )

            Text("Transport Mode:")
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(
                    selected = transportMode == TransportMode.SPEAKER,
                    onClick = { transportMode = TransportMode.SPEAKER }
                )
                Text("Speaker (Local)")
                Spacer(modifier = Modifier.width(16.dp))
                RadioButton(
                    selected = transportMode == TransportMode.BLUETOOTH,
                    onClick = { transportMode = TransportMode.BLUETOOTH }
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
                    color = MaterialTheme.colorScheme.primary
                )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = useStereo,
                    onCheckedChange = { useStereo = it }
                )
                Text("Stereo (Requires Restart)")
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = enableAGC,
                    onCheckedChange = { enableAGC = it }
                )
                Text("Auto Gain Control")
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = enableNS,
                    onCheckedChange = { enableNS = it }
                )
                Text("Noise Suppression")
            }

            Text("Microphone Source:")
            SourceOption("Default", MediaRecorder.AudioSource.MIC, micSource) { micSource = it }
            SourceOption("Camcorder", MediaRecorder.AudioSource.CAMCORDER, micSource) { micSource = it }
            SourceOption("Unprocessed", MediaRecorder.AudioSource.UNPROCESSED, micSource) { micSource = it }
            SourceOption("Voice Rec", MediaRecorder.AudioSource.VOICE_RECOGNITION, micSource) { micSource = it }

            Spacer(modifier = Modifier.height(20.dp))
            Text(
                text = "Bluetooth mode now uses a lower-rate mic stream for better stability, then the Windows receiver expands it back into BM Mic.",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }

    private fun startMic(enableBluetooth: Boolean) {
        val intent = Intent(this, MicService::class.java).apply {
            putExtra(MicService.EXTRA_ENABLE_BT, enableBluetooth)
            putExtra(MicService.EXTRA_MUTE_LOCAL, enableBluetooth)
        }
        startForegroundService(intent)
    }

    private fun stopMic() {
        val intent = Intent(this, MicService::class.java).apply {
            action = MicService.ACTION_STOP
        }
        startService(intent)
    }

    @Composable
    fun SourceOption(label: String, value: Int, current: Int, onSelect: (Int) -> Unit) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            RadioButton(
                selected = value == current,
                onClick = { onSelect(value) }
            )
            Text(label)
        }
    }

    enum class TransportMode {
        SPEAKER,
        BLUETOOTH,
    }
}
