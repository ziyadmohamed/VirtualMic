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
    ULONG m_Count;
    KSPIN_LOCK m_Lock;

    void DropOldestLocked(ULONG length) {
        if (length >= m_Count) {
            m_ReadPtr = m_WritePtr;
            m_Count = 0;
            return;
        }

        m_ReadPtr = (m_ReadPtr + length) % m_Size;
        m_Count -= length;
    }

    void CopyInLocked(const BYTE* data, ULONG length) {
        ULONG firstCopy = min(length, m_Size - m_WritePtr);
        RtlCopyMemory(m_Buffer + m_WritePtr, data, firstCopy);
        if (length > firstCopy) {
            RtlCopyMemory(m_Buffer, data + firstCopy, length - firstCopy);
        }

        m_WritePtr = (m_WritePtr + length) % m_Size;
        m_Count += length;
    }

    ULONG CopyOutLocked(BYTE* dest, ULONG length) {
        ULONG available = min(length, m_Count);
        ULONG firstCopy = min(available, m_Size - m_ReadPtr);

        if (available > 0) {
            RtlCopyMemory(dest, m_Buffer + m_ReadPtr, firstCopy);
            if (available > firstCopy) {
                RtlCopyMemory(dest + firstCopy, m_Buffer, available - firstCopy);
            }

            m_ReadPtr = (m_ReadPtr + available) % m_Size;
            m_Count -= available;
        }

        return available;
    }

public:
    // Removed Singleton to avoid kernel static init issues
    // Use global g_SidebandData

    void Init(ULONG size) {
        if (!m_Buffer) {
            m_Buffer = (BYTE*)ExAllocatePoolWithTag(NonPagedPoolNx, size, 'CISB');
            m_Size = size;
            m_ReadPtr = 0;
            m_WritePtr = 0;
            m_Count = 0;
            KeInitializeSpinLock(&m_Lock);
        }
    }

    void Free() {
        if (m_Buffer) {
            ExFreePoolWithTag(m_Buffer, 'CISB');
            m_Buffer = NULL;
            m_Size = 0;
            m_ReadPtr = 0;
            m_WritePtr = 0;
            m_Count = 0;
        }
    }

    void Write(const BYTE* data, ULONG length) {
        if (!m_Buffer || !data || length == 0) return;

        if (length > m_Size) {
            data += (length - m_Size);
            length = m_Size;
        }
        
        KIRQL oldIrql;
        KeAcquireSpinLock(&m_Lock, &oldIrql);

        ULONG freeSpace = m_Size - m_Count;
        if (length > freeSpace) {
            DropOldestLocked(length - freeSpace);
        }

        CopyInLocked(data, length);

        KeReleaseSpinLock(&m_Lock, oldIrql);
    }

    void Read(BYTE* dest, ULONG length) {
        if (!m_Buffer) {
            RtlZeroMemory(dest, length);
            return;
        }

        KIRQL oldIrql;
        KeAcquireSpinLock(&m_Lock, &oldIrql);

        ULONG copied = CopyOutLocked(dest, length);
        if (copied < length) {
            RtlZeroMemory(dest + copied, length - copied);
        }

        KeReleaseSpinLock(&m_Lock, oldIrql);
    }
    
    // Constructor
    SidebandData() : m_Buffer(NULL), m_Size(0), m_ReadPtr(0), m_WritePtr(0), m_Count(0) {}
};

// Global instance declaration
extern SidebandData g_SidebandData;

#endif
