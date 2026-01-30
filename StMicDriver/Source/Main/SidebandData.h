#ifndef _SIDEBAND_DATA_H_
#define _SIDEBAND_DATA_H_

#include "definitions.h"

// Simple Circular Buffer
class SidebandData {
private:
    BYTE* m_Buffer;
    ULONG m_Size;
    ULONG m_ReadPtr;
    ULONG m_WritePtr;
    KSPIN_LOCK m_Lock;

public:
    // Removed Singleton to avoid kernel static init issues
    // Use global g_SidebandData

    void Init(ULONG size) {
        if (!m_Buffer) {
            m_Buffer = (BYTE*)ExAllocatePoolWithTag(NonPagedPoolNx, size, 'CISB');
            m_Size = size;
            m_ReadPtr = 0;
            m_WritePtr = 0;
            KeInitializeSpinLock(&m_Lock);
        }
    }

    void Free() {
        if (m_Buffer) {
            ExFreePoolWithTag(m_Buffer, 'CISB');
            m_Buffer = NULL;
            m_Size = 0;
        }
    }

    void Write(BYTE* data, ULONG length) {
        if (!m_Buffer) return;
        
        KIRQL oldIrql;
        KeAcquireSpinLock(&m_Lock, &oldIrql);

        for (ULONG i = 0; i < length; i++) {
            m_Buffer[m_WritePtr] = data[i];
            m_WritePtr = (m_WritePtr + 1) % m_Size;
            
            // If full, advance read ptr (overwrite oldest)
            if (m_WritePtr == m_ReadPtr) {
                m_ReadPtr = (m_ReadPtr + 1) % m_Size;
            }
        }

        KeReleaseSpinLock(&m_Lock, oldIrql);
    }

    void Read(BYTE* dest, ULONG length) {
        if (!m_Buffer) {
            RtlZeroMemory(dest, length);
            return;
        }

        KIRQL oldIrql;
        KeAcquireSpinLock(&m_Lock, &oldIrql);

        for (ULONG i = 0; i < length; i++) {
            if (m_ReadPtr != m_WritePtr) {
                dest[i] = m_Buffer[m_ReadPtr];
                m_ReadPtr = (m_ReadPtr + 1) % m_Size;
            } else {
                dest[i] = 0; // Buffer empty, pad with silence
            }
        }

        KeReleaseSpinLock(&m_Lock, oldIrql);
    }
    
    // Constructor
    SidebandData() : m_Buffer(NULL), m_Size(0) {}
};

// Global instance declaration
extern SidebandData g_SidebandData;

#endif
