package org.blindmasters.StMic

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.UUID

class BluetoothServer(
    private val serviceName: String = DEFAULT_SERVICE_NAME,
    uuidString: String = DEFAULT_UUID_STRING,
    private val onConnected: (BluetoothSocket) -> Unit,
) {

    private var acceptJob: Job? = null
    private var serverSocket: BluetoothServerSocket? = null
    private var clientSocket: BluetoothSocket? = null
    private val uuid: UUID = UUID.fromString(uuidString)
    private val adapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    
    var isRunning = false
        private set

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRunning) return
        if (adapter == null || !adapter.isEnabled) {
            Log.e("BluetoothServer", "Bluetooth not ready")
            return
        }

        try {
            serverSocket = adapter.listenUsingRfcommWithServiceRecord(serviceName, uuid)
            isRunning = true
            
            acceptJob = CoroutineScope(Dispatchers.IO).launch {
                Log.d("BluetoothServer", "Waiting for connection...")
                while (isActive && isRunning) {
                    val socket = try {
                        serverSocket?.accept()
                    } catch (e: IOException) {
                        if (isRunning) {
                            Log.e("BluetoothServer", "Socket accept failed", e)
                        }
                        break
                    }

                    if (socket == null) {
                        continue
                    }

                    try {
                        clientSocket = socket
                        Log.d("BluetoothServer", "Accepted connection from ${socket.remoteDevice.name}")
                        onConnected(socket)
                    } catch (e: Exception) {
                        Log.e("BluetoothServer", "Connection handoff failed", e)
                        try {
                            socket.close()
                        } catch (_: IOException) {
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("BluetoothServer", "Listen failed", e)
            stop()
        }
    }

    fun stop() {
        isRunning = false
        closeClientSocket()
        closeServerSocket()
        acceptJob?.cancel()
    }
    
    private fun closeServerSocket() {
        try {
            serverSocket?.close()
        } catch (e: IOException) {
            Log.e("BluetoothServer", "Could not close server socket", e)
        }
        serverSocket = null
    }

    private fun closeClientSocket() {
        try {
            clientSocket?.close()
        } catch (e: IOException) {
            Log.e("BluetoothServer", "Could not close client socket", e)
        }
        clientSocket = null
    }

    companion object {
        const val DEFAULT_SERVICE_NAME = "StMic"
        const val DEFAULT_UUID_STRING = "00001101-0000-1000-8000-00805F9B34FB"
    }
}
