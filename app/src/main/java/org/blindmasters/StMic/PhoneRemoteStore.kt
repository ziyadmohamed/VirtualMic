package org.blindmasters.StMic

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PhoneRemoteState(
    val serverRunning: Boolean = false,
    val clientConnected: Boolean = false,
    val bluetoothServiceName: String = PhoneRemoteConfig.SERVICE_NAME,
    val bluetoothServiceUuid: String = PhoneRemoteConfig.SERVICE_UUID,
    val telephonyState: String = "IDLE",
    val callState: String = "IDLE",
    val primaryNumber: String = "",
    val isDefaultDialer: Boolean = false,
    val callControlAvailable: Boolean = false,
    val canAnswer: Boolean = false,
    val canHangUp: Boolean = false,
    val isMuted: Boolean = false,
    val audioRoute: String = "EARPIECE",
    val availableAudioRoutes: List<String> = emptyList(),
    val lastDialedNumber: String = "",
    val lastSmsTarget: String = "",
    val lastSmsPreview: String = "",
    val lastError: String? = null,
)

object PhoneRemoteConfig {
    const val SERVICE_NAME = "StMic Phone Remote"
    const val SERVICE_UUID = "bb807b4d-aea5-4f11-a8b1-47d12ae2f4c2"
}

object PhoneRemoteStore {
    private val mutableState = MutableStateFlow(PhoneRemoteState())
    val state = mutableState.asStateFlow()

    fun update(transform: (PhoneRemoteState) -> PhoneRemoteState) {
        mutableState.value = transform(mutableState.value)
    }
}
