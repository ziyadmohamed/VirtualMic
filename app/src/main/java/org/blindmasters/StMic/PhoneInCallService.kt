package org.blindmasters.StMic

import android.telecom.Call
import android.telecom.CallAudioState
import android.telecom.InCallService

class PhoneInCallService : InCallService() {

    override fun onCreate() {
        super.onCreate()
        PhoneInCallCoordinator.attachService(this)
    }

    override fun onCallAdded(call: Call) {
        super.onCallAdded(call)
        PhoneInCallCoordinator.onCallAdded(call)
    }

    override fun onCallRemoved(call: Call) {
        PhoneInCallCoordinator.onCallRemoved(call)
        super.onCallRemoved(call)
    }

    override fun onCallAudioStateChanged(audioState: CallAudioState) {
        super.onCallAudioStateChanged(audioState)
        PhoneInCallCoordinator.onCallAudioStateChanged(audioState)
    }

    override fun onDestroy() {
        PhoneInCallCoordinator.detachService(this)
        super.onDestroy()
    }
}
