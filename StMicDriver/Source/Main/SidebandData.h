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
    static SidebandData& GetInstance() {
        static SidebandData instance;
        return instance;
    }

    void Init(ULONG size) {
        if (!m_Buffer) {
            m_Buffer = (BYTE*)ExAllocatePool2(POOL_FLAG_NON_PAGED, size, 'CISB');
            m_Size = size;
            m_ReadPtr = 0;
            m_WritePtr = 0;
            KeInitializeSpinLock(&m_Lock);
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
    
private:
    SidebandData() : m_Buffer(NULL), m_Size(0) {}
};

#endif
