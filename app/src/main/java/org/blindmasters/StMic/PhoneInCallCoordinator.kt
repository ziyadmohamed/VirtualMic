package org.blindmasters.StMic

import android.net.Uri
import android.telecom.Call
import android.telecom.CallAudioState
import android.telecom.VideoProfile

object PhoneInCallCoordinator {

    private var inCallService: PhoneInCallService? = null
    private val trackedCalls = linkedSetOf<Call>()
    private val callbacks = mutableMapOf<Call, Call.Callback>()
    private var isMuted = false
    private var audioRoute = CallAudioState.ROUTE_WIRED_OR_EARPIECE
    private var supportedRouteMask = CallAudioState.ROUTE_EARPIECE or CallAudioState.ROUTE_SPEAKER

    fun attachService(service: PhoneInCallService) {
        inCallService = service
        refreshState()
    }

    fun detachService(service: PhoneInCallService) {
        if (inCallService === service) {
            inCallService = null
        }
        refreshState()
    }

    fun onCallAdded(call: Call) {
        trackedCalls += call
        val callback = object : Call.Callback() {
            override fun onStateChanged(call: Call, state: Int) {
                refreshState()
            }

            override fun onDetailsChanged(call: Call, details: Call.Details) {
                refreshState()
            }

            override fun onCallDestroyed(call: Call) {
                onCallRemoved(call)
            }
        }
        callbacks[call] = callback
        call.registerCallback(callback)
        refreshState()
    }

    fun onCallRemoved(call: Call) {
        callbacks.remove(call)?.let(call::unregisterCallback)
        trackedCalls -= call
        refreshState()
    }

    fun onCallAudioStateChanged(state: CallAudioState?) {
        if (state != null) {
            isMuted = state.isMuted
            audioRoute = state.route
            supportedRouteMask = state.supportedRouteMask
        }
        refreshState()
    }

    fun answer(): Result<String> {
        val call = selectPrimaryCall()
            ?: return Result.failure(IllegalStateException("No active or ringing call is available"))
        if (call.state != Call.STATE_RINGING) {
            return Result.failure(IllegalStateException("The current call is not ringing"))
        }
        call.answer(VideoProfile.STATE_AUDIO_ONLY)
        return Result.success("Answer requested")
    }

    fun disconnect(): Result<String> {
        val call = selectPrimaryCall()
            ?: return Result.failure(IllegalStateException("No active call is available"))
        call.disconnect()
        return Result.success("Disconnect requested")
    }

    fun setMuted(muted: Boolean): Result<String> {
        val service = inCallService
            ?: return Result.failure(IllegalStateException("Call controls require the app to be the default dialer during a live call"))
        service.setMuted(muted)
        isMuted = muted
        refreshState()
        return Result.success(if (muted) "Microphone muted" else "Microphone unmuted")
    }

    fun setSpeakerEnabled(enabled: Boolean): Result<String> {
        val service = inCallService
            ?: return Result.failure(IllegalStateException("Call controls require the app to be the default dialer during a live call"))
        val targetRoute = if (enabled) {
            CallAudioState.ROUTE_SPEAKER
        } else {
            defaultNonSpeakerRoute()
        }
        if (!isRouteSupported(targetRoute)) {
            return Result.failure(IllegalStateException("Requested audio route is not currently available"))
        }
        service.setAudioRoute(targetRoute)
        audioRoute = targetRoute
        refreshState()
        return Result.success(if (enabled) "Speaker enabled" else "Speaker disabled")
    }

    fun setAudioRoute(routeName: String): Result<String> {
        val service = inCallService
            ?: return Result.failure(IllegalStateException("Call controls require the app to be the default dialer during a live call"))
        val targetRoute = routeConstantFor(routeName)
            ?: return Result.failure(IllegalArgumentException("Unknown route: $routeName"))
        if (!isRouteSupported(targetRoute)) {
            return Result.failure(IllegalStateException("Route $routeName is not currently available"))
        }
        service.setAudioRoute(targetRoute)
        audioRoute = targetRoute
        refreshState()
        return Result.success("Audio route switched to ${routeLabel(targetRoute)}")
    }

    private fun selectPrimaryCall(): Call? {
        return trackedCalls.maxByOrNull(::priorityForState)
    }

    private fun priorityForState(call: Call): Int {
        return when (call.state) {
            Call.STATE_RINGING -> 6
            Call.STATE_ACTIVE -> 5
            Call.STATE_DIALING -> 4
            Call.STATE_CONNECTING -> 3
            Call.STATE_HOLDING -> 2
            Call.STATE_DISCONNECTING -> 1
            else -> 0
        }
    }

    private fun refreshState() {
        val primaryCall = selectPrimaryCall()
        PhoneRemoteStore.update { current ->
            current.copy(
                callState = primaryCall?.let { labelForCallState(it.state) } ?: fallbackCallState(current.telephonyState),
                primaryNumber = primaryCall?.details?.handle?.safeNumber().orEmpty(),
                callControlAvailable = inCallService != null,
                canAnswer = primaryCall?.state == Call.STATE_RINGING,
                canHangUp = primaryCall != null && primaryCall.state != Call.STATE_DISCONNECTED,
                isMuted = primaryCall != null && isMuted,
                audioRoute = routeLabel(audioRoute),
                availableAudioRoutes = availableRoutesFromMask(supportedRouteMask),
            )
        }
    }

    private fun fallbackCallState(telephonyState: String): String {
        return when (telephonyState) {
            "RINGING" -> "RINGING"
            "OFFHOOK" -> "OFFHOOK"
            else -> "IDLE"
        }
    }

    private fun labelForCallState(state: Int): String {
        return when (state) {
            Call.STATE_NEW -> "NEW"
            Call.STATE_DIALING -> "DIALING"
            Call.STATE_RINGING -> "RINGING"
            Call.STATE_ACTIVE -> "ACTIVE"
            Call.STATE_HOLDING -> "HOLDING"
            Call.STATE_DISCONNECTED -> "DISCONNECTED"
            Call.STATE_SELECT_PHONE_ACCOUNT -> "SELECT_ACCOUNT"
            Call.STATE_CONNECTING -> "CONNECTING"
            Call.STATE_DISCONNECTING -> "DISCONNECTING"
            Call.STATE_PULLING_CALL -> "PULLING"
            Call.STATE_AUDIO_PROCESSING -> "AUDIO_PROCESSING"
            Call.STATE_SIMULATED_RINGING -> "SIMULATED_RINGING"
            else -> "UNKNOWN"
        }
    }

    private fun routeLabel(route: Int): String {
        return when {
            route and CallAudioState.ROUTE_SPEAKER != 0 -> "SPEAKER"
            route and CallAudioState.ROUTE_BLUETOOTH != 0 -> "BLUETOOTH"
            route and CallAudioState.ROUTE_WIRED_HEADSET != 0 -> "WIRED_HEADSET"
            else -> "EARPIECE"
        }
    }

    private fun availableRoutesFromMask(mask: Int): List<String> {
        val routes = mutableListOf<String>()
        if (mask and CallAudioState.ROUTE_EARPIECE != 0) {
            routes += "EARPIECE"
        }
        if (mask and CallAudioState.ROUTE_WIRED_HEADSET != 0) {
            routes += "WIRED_HEADSET"
        }
        if (mask and CallAudioState.ROUTE_BLUETOOTH != 0) {
            routes += "BLUETOOTH"
        }
        if (mask and CallAudioState.ROUTE_SPEAKER != 0) {
            routes += "SPEAKER"
        }
        return routes
    }

    private fun routeConstantFor(routeName: String): Int? {
        return when (routeName.trim().uppercase()) {
            "EARPIECE" -> CallAudioState.ROUTE_EARPIECE
            "WIRED_HEADSET", "WIRED" -> CallAudioState.ROUTE_WIRED_HEADSET
            "BLUETOOTH", "BT" -> CallAudioState.ROUTE_BLUETOOTH
            "SPEAKER", "SPEAKERPHONE" -> CallAudioState.ROUTE_SPEAKER
            else -> null
        }
    }

    private fun isRouteSupported(route: Int): Boolean {
        return supportedRouteMask and route != 0
    }

    private fun defaultNonSpeakerRoute(): Int {
        return when {
            isRouteSupported(CallAudioState.ROUTE_BLUETOOTH) -> CallAudioState.ROUTE_BLUETOOTH
            isRouteSupported(CallAudioState.ROUTE_WIRED_HEADSET) -> CallAudioState.ROUTE_WIRED_HEADSET
            isRouteSupported(CallAudioState.ROUTE_EARPIECE) -> CallAudioState.ROUTE_EARPIECE
            else -> CallAudioState.ROUTE_WIRED_OR_EARPIECE
        }
    }

    private fun Uri.safeNumber(): String {
        return schemeSpecificPart.orEmpty()
    }
}
