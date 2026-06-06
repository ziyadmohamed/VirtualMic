package org.blindmasters.StMic

import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.telecom.TelecomManager
import android.telephony.SmsManager
import androidx.core.content.ContextCompat
import androidx.core.os.bundleOf

class PhoneController(private val context: Context) {

    private val packageManager = context.packageManager
    private val telecomManager = context.getSystemService(TelecomManager::class.java)
    private val roleManager = context.getSystemService(RoleManager::class.java)

    fun refreshRoleState() {
        PhoneRemoteStore.update { current ->
            current.copy(isDefaultDialer = isDefaultDialer())
        }
    }

    fun dial(number: String, speakerphone: Boolean = false): Result<String> {
        return runCatching {
            requireFeature(PackageManager.FEATURE_TELEPHONY_CALLING, "This device does not support phone calls")
            requirePermission(Manifest.permission.CALL_PHONE)
            val sanitized = sanitizeNumber(number)
            val extras = bundleOf(TelecomManager.EXTRA_START_CALL_WITH_SPEAKERPHONE to speakerphone)
            telecomManager.placeCall(Uri.fromParts("tel", sanitized, null), extras)
            PhoneRemoteStore.update { current ->
                current.copy(
                    lastDialedNumber = sanitized,
                    lastError = null,
                )
            }
            "Dial requested"
        }.also(::reflectResult)
    }

    fun sendSms(number: String, message: String): Result<String> {
        return runCatching {
            requireFeature(PackageManager.FEATURE_TELEPHONY_MESSAGING, "This device does not support SMS")
            requirePermission(Manifest.permission.SEND_SMS)
            val sanitized = sanitizeNumber(number)
            val trimmedMessage = message.trim()
            require(trimmedMessage.isNotEmpty()) { "Message body is required" }

            val smsManager = SmsManager.getDefault()
            val parts = smsManager.divideMessage(trimmedMessage)
            if (parts.size > 1) {
                smsManager.sendMultipartTextMessage(sanitized, null, parts, null, null)
            } else {
                smsManager.sendTextMessage(sanitized, null, trimmedMessage, null, null)
            }

            PhoneRemoteStore.update { current ->
                current.copy(
                    lastSmsTarget = sanitized,
                    lastSmsPreview = trimmedMessage.take(64),
                    lastError = null,
                )
            }
            "SMS queued"
        }.also(::reflectResult)
    }

    fun answerCall(): Result<String> {
        return PhoneInCallCoordinator.answer().also(::reflectResult)
    }

    fun hangUpCall(): Result<String> {
        return PhoneInCallCoordinator.disconnect().also(::reflectResult)
    }

    fun setMuted(muted: Boolean): Result<String> {
        return PhoneInCallCoordinator.setMuted(muted).also(::reflectResult)
    }

    fun setSpeakerphone(enabled: Boolean): Result<String> {
        return PhoneInCallCoordinator.setSpeakerEnabled(enabled).also(::reflectResult)
    }

    fun setAudioRoute(route: String): Result<String> {
        return PhoneInCallCoordinator.setAudioRoute(route).also(::reflectResult)
    }

    fun isDefaultDialer(): Boolean {
        return roleManager?.isRoleHeld(RoleManager.ROLE_DIALER) == true
    }

    private fun sanitizeNumber(number: String): String {
        val trimmed = number.trim()
        require(trimmed.isNotEmpty()) { "Phone number is required" }
        return trimmed
    }

    private fun requireFeature(feature: String, message: String) {
        check(packageManager.hasSystemFeature(feature)) { message }
    }

    private fun requirePermission(permission: String) {
        check(
            ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
        ) { "Missing runtime permission: $permission" }
    }

    private fun reflectResult(result: Result<String>) {
        PhoneRemoteStore.update { current ->
            current.copy(lastError = result.exceptionOrNull()?.message)
        }
    }
}
