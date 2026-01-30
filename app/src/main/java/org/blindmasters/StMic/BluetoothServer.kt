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

class BluetoothServer(private val onConnected: (BluetoothSocket) -> Unit) {

    private var acceptJob: Job? = null
    private var serverSocket: BluetoothServerSocket? = null
    private val uuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB") // Standard SPP UUID
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
            // "StMic" is the Service Name, UUID is the Service ID
            serverSocket = adapter.listenUsingRfcommWithServiceRecord("StMic", uuid)
            isRunning = true
            
            acceptJob = CoroutineScope(Dispatchers.IO).launch {
                Log.d("BluetoothServer", "Waiting for connection...")
                var socket: BluetoothSocket? = null
                while (isActive && isRunning) {
                    try {
                        socket = serverSocket?.accept()
                    } catch (e: IOException) {
                        Log.e("BluetoothServer", "Socket accept failed", e)
                        break
                    }

                    if (socket != null) {
                        Log.d("BluetoothServer", "Accepted connection from ${socket.remoteDevice.name}")
                        // Manage the connection in a separate thread/helper
                        // For now, we just pass it back to the service
                        onConnected(socket)
                        
                        // We only want one connection for now, so close the server socket
                        closeServerSocket() 
                        break
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
}
