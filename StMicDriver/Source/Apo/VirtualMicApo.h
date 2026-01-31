#pragma once

#include <windows.h>
#include <mmreg.h>
#include <audioenginebaseapo.h>

// {A4B73D9A-7D0E-4E7B-9E4D-9D6D3C1A9B2F}
static const GUID CLSID_VirtualMicApo =
{ 0xa4b73d9a, 0x7d0e, 0x4e7b, { 0x9e, 0x4d, 0x9d, 0x6d, 0x3c, 0x1a, 0x9b, 0x2f } };

class VirtualMicApo final : public IAudioProcessingObject,
                           public IAudioProcessingObjectRT,
                           public IAudioProcessingObjectConfiguration
{
public:
    VirtualMicApo();
    virtual ~VirtualMicApo();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    STDMETHODIMP_(ULONG) AddRef() override;
    STDMETHODIMP_(ULONG) Release() override;

    // IAudioProcessingObject
    STDMETHODIMP Reset() override;
    STDMETHODIMP GetLatency(HNSTIME* pLatency) override;
    STDMETHODIMP GetRegistrationProperties(APO_REG_PROPERTIES** ppRegProps) override;
    STDMETHODIMP Initialize(UINT32 cbDataSize, BYTE* pbyData) override;
    STDMETHODIMP IsInputFormatSupported(IAudioMediaType* pOutputFormat,
                                        IAudioMediaType* pRequestedInputFormat,
                                        IAudioMediaType** ppSupportedInputFormat) override;
    STDMETHODIMP IsOutputFormatSupported(IAudioMediaType* pInputFormat,
                                         IAudioMediaType* pRequestedOutputFormat,
                                         IAudioMediaType** ppSupportedOutputFormat) override;
    STDMETHODIMP GetInputChannelCount(UINT32* pChannelCount) override;

    // IAudioProcessingObjectRT
    STDMETHODIMP_(void) APOProcess(UINT32 u32NumInputConnections,
                                   APO_CONNECTION_PROPERTY** ppInputConnections,
                                   UINT32 u32NumOutputConnections,
                                   APO_CONNECTION_PROPERTY** ppOutputConnections) override;
    STDMETHODIMP_(UINT32) CalcInputFrames(UINT32 u32OutputFrames) override;
    STDMETHODIMP_(UINT32) CalcOutputFrames(UINT32 u32InputFrames) override;

    // IAudioProcessingObjectConfiguration
    STDMETHODIMP LockForProcess(UINT32 u32NumInputConnections,
                                APO_CONNECTION_DESCRIPTOR** ppInputConnections,
                                UINT32 u32NumOutputConnections,
                                APO_CONNECTION_DESCRIPTOR** ppOutputConnections) override;
    STDMETHODIMP UnlockForProcess() override;

private:
    LONG m_refCount;
    UINT32 m_channels;
    UINT32 m_bytesPerFrame;
};

class VirtualMicApoClassFactory final : public IClassFactory
{
public:
    VirtualMicApoClassFactory();

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override;
    STDMETHODIMP_(ULONG) AddRef() override;
    STDMETHODIMP_(ULONG) Release() override;

    // IClassFactory
    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override;
    STDMETHODIMP LockServer(BOOL fLock) override;

private:
    LONG m_refCount;
};

HRESULT DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv);
HRESULT DllCanUnloadNow();
