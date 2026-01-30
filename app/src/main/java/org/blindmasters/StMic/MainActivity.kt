package org.blindmasters.StMic

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.media.MediaRecorder
import android.os.Bundle
import android.os.IBinder
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
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
        
        permissionLauncher.launch(
            arrayOf(
                android.Manifest.permission.RECORD_AUDIO,
                android.Manifest.permission.POST_NOTIFICATIONS
            )
        )

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
        super.onStop()
        unbindService(connection)
        isBound = false
    }

    @Composable
    fun MainScreen() {
        var isRunning by remember { mutableStateOf(false) }
        var gain by remember { mutableFloatStateOf(1.0f) }
        var micSource by remember { mutableIntStateOf(MediaRecorder.AudioSource.MIC) }
        var useStereo by remember { mutableStateOf(false) }
        var enableAGC by remember { mutableStateOf(false) }
        var useStereo by remember { mutableStateOf(false) }
        var enableAGC by remember { mutableStateOf(false) }
        var enableNS by remember { mutableStateOf(false) }
        var transportMode by remember { mutableStateOf(TransportMode.SPEAKER) }
        var btStatus by remember { mutableStateOf(false) }

        // Poll service state
        LaunchedEffect(Unit) {
             while(true) {
                 if (isBound && micService != null) {
                 if (isBound && micService != null) {
                    isRunning = micService!!.audioEngine.isRunning
                    btStatus = micService!!.isBtRunning
                    // Sync initial state if needed, but UI drives state mostly
                 }
                 kotlinx.coroutines.delay(1000)
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
                         val intent = Intent(this@MainActivity, MicService::class.java)
                         intent.action = MicService.ACTION_STOP
                         startService(intent)
                    } else {
                        // Apply settings before start
                        micService?.audioEngine?.let {
                            it.gainFactor = gain
                            it.selectedSource = micSource
                            it.useStereo = useStereo
                            it.enableAGC = enableAGC
                            it.enableNS = enableNS
                        }
                            it.enableAGC = enableAGC
                            it.enableNS = enableNS
                        }
                        val intent = Intent(this@MainActivity, MicService::class.java)
                        intent.putExtra(MicService.EXTRA_ENABLE_BT, transportMode == TransportMode.BLUETOOTH)
                        intent.putExtra(MicService.EXTRA_MUTE_LOCAL, transportMode == TransportMode.BLUETOOTH)
                        startForegroundService(intent)
                    }
                    // State updates via polling or immediate optimized feedback
                    isRunning = !isRunning 
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
                    selected = (transportMode == TransportMode.SPEAKER),
                    onClick = { transportMode = TransportMode.SPEAKER }
                )
                Text("Speaker (Local)")
                Spacer(modifier = Modifier.width(16.dp))
                RadioButton(
                    selected = (transportMode == TransportMode.BLUETOOTH),
                    onClick = { transportMode = TransportMode.BLUETOOTH }
                )
                Text("Bluetooth (PC)")
            }
            if (isRunning && transportMode == TransportMode.BLUETOOTH) {
                 Text(
                     text = if (btStatus) "Bluetooth Server Running (Waiting for connection...)" else "Bluetooth Stopped",
                     style = MaterialTheme.typography.bodySmall,
                     color = MaterialTheme.colorScheme.primary
                 )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = useStereo, onCheckedChange = { 
                    useStereo = it
                    // Restart required for format change
                 })
                Text("Stereo (Requires Restart)")
            }
            
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = enableAGC, onCheckedChange = { 
                    enableAGC = it
                    micService?.audioEngine?.enableAGC = it // Engine handles dynamic if implemented, else restart
                 })
                Text("Auto Gain Control")
            }
            
            Row(verticalAlignment = Alignment.CenterVertically) {
                 Checkbox(checked = enableNS, onCheckedChange = { 
                    enableNS = it
                 })
                Text("Noise Suppression")
            }

            Text("Microphone Source:")
            // Simple radio buttons for source
            SourceOption("Default", MediaRecorder.AudioSource.MIC, micSource) { micSource = it }
            SourceOption("Camcorder", MediaRecorder.AudioSource.CAMCORDER, micSource) { micSource = it }
            SourceOption("Unprocessed", MediaRecorder.AudioSource.UNPROCESSED, micSource) { micSource = it }
            SourceOption("Voice Rec", MediaRecorder.AudioSource.VOICE_RECOGNITION, micSource) { micSource = it }
            
            Spacer(modifier = Modifier.height(20.dp))
            Text("Note: To use as input for other apps, connect Headphone Jack to Mic Jack (Loopback) or rely on system mixing behaviors.", style = MaterialTheme.typography.bodySmall)
        }
    }
    
    @Composable
    fun SourceOption(label: String, value: Int, current: Int, onSelect: (Int) -> Unit) {
         Row(verticalAlignment = Alignment.CenterVertically) {
            RadioButton(
                selected = (value == current),
                onClick = { onSelect(value) }
            )
            Text(label)
        }
    }
    }
    
    enum class TransportMode {
        SPEAKER, BLUETOOTH
    }
}
