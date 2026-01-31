#include "VirtualMicApo.h"
#include <new>

static LONG g_dllRef = 0;

VirtualMicApo::VirtualMicApo()
    : m_refCount(1),
      m_channels(1),
      m_bytesPerFrame(2)
{
    InterlockedIncrement(&g_dllRef);
}

VirtualMicApo::~VirtualMicApo()
{
    InterlockedDecrement(&g_dllRef);
}

STDMETHODIMP VirtualMicApo::QueryInterface(REFIID riid, void** ppv)
{
    if (!ppv) return E_POINTER;
    *ppv = nullptr;

    if (riid == __uuidof(IUnknown) ||
        riid == __uuidof(IAudioProcessingObject) ||
        riid == __uuidof(IAudioProcessingObjectRT))
    {
        *ppv = static_cast<IAudioProcessingObjectRT*>(this);
    }
    else if (riid == __uuidof(IAudioProcessingObject))
    {
        *ppv = static_cast<IAudioProcessingObject*>(this);
    }
    else if (riid == __uuidof(IAudioProcessingObjectRT))
    {
        *ppv = static_cast<IAudioProcessingObjectRT*>(this);
    }

    if (*ppv)
    {
        AddRef();
        return S_OK;
    }

    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) VirtualMicApo::AddRef()
{
    return (ULONG)InterlockedIncrement(&m_refCount);
}

STDMETHODIMP_(ULONG) VirtualMicApo::Release()
{
    ULONG ref = (ULONG)InterlockedDecrement(&m_refCount);
    if (ref == 0)
    {
        delete this;
    }
    return ref;
}

STDMETHODIMP VirtualMicApo::GetLatency(HNSTIME* pLatency)
{
    if (!pLatency) return E_POINTER;
    *pLatency = 0;
    return S_OK;
}

STDMETHODIMP VirtualMicApo::Initialize(UINT32 /*cbDataSize*/, BYTE* /*pbyData*/)
{
    return S_OK;
}

STDMETHODIMP VirtualMicApo::IsInputFormatSupported(IAudioMediaType* /*pOutputFormat*/,
                                                   IAudioMediaType* pRequestedInputFormat,
                                                   IAudioMediaType** ppSupportedInputFormat)
{
    if (!pRequestedInputFormat) return E_POINTER;
    if (ppSupportedInputFormat) *ppSupportedInputFormat = nullptr;
    return S_OK;
}

STDMETHODIMP VirtualMicApo::IsOutputFormatSupported(IAudioMediaType* /*pInputFormat*/,
                                                    IAudioMediaType* pRequestedOutputFormat,
                                                    IAudioMediaType** ppSupportedOutputFormat)
{
    if (!pRequestedOutputFormat) return E_POINTER;
    if (ppSupportedOutputFormat) *ppSupportedOutputFormat = nullptr;
    return S_OK;
}

STDMETHODIMP VirtualMicApo::GetInputChannelCount(UINT32* pChannelCount)
{
    if (!pChannelCount) return E_POINTER;
    *pChannelCount = m_channels;
    return S_OK;
}

STDMETHODIMP VirtualMicApo::GetOutputChannelCount(UINT32* pChannelCount)
{
    if (!pChannelCount) return E_POINTER;
    *pChannelCount = m_channels;
    return S_OK;
}

STDMETHODIMP VirtualMicApo::LockForProcess(UINT32 /*u32NumInputConnections*/,
                                           APO_CONNECTION_DESCRIPTOR** /*ppInputConnections*/,
                                           UINT32 /*u32NumOutputConnections*/,
                                           APO_CONNECTION_DESCRIPTOR** ppOutputConnections)
{
    if (!ppOutputConnections || !ppOutputConnections[0]) return E_POINTER;
    IAudioMediaType* fmt = ppOutputConnections[0]->pFormat;
    if (fmt)
    {
        WAVEFORMATEX* wfx = nullptr;
        if (SUCCEEDED(fmt->GetAudioFormat(&wfx)) && wfx)
        {
            m_channels = wfx->nChannels;
            m_bytesPerFrame = wfx->nBlockAlign;
        }
    }
    return S_OK;
}

STDMETHODIMP VirtualMicApo::UnlockForProcess()
{
    return S_OK;
}

STDMETHODIMP_(void) VirtualMicApo::APOProcess(UINT32 u32NumInputConnections,
                                              APO_CONNECTION_PROPERTY** ppInputConnections,
                                              UINT32 u32NumOutputConnections,
                                              APO_CONNECTION_PROPERTY** ppOutputConnections)
{
    if (u32NumOutputConnections == 0 || !ppOutputConnections || !ppOutputConnections[0])
    {
        return;
    }

    APO_CONNECTION_PROPERTY* outConn = ppOutputConnections[0];
    if (!outConn->pBuffer)
    {
        return;
    }

    UINT32 frames = outConn->u32ValidFrameCount;
    UINT32 bytes = frames * m_bytesPerFrame;

    if (u32NumInputConnections == 0 || !ppInputConnections || !ppInputConnections[0] || !ppInputConnections[0]->pBuffer)
    {
        memset(outConn->pBuffer, 0, bytes);
        return;
    }

    APO_CONNECTION_PROPERTY* inConn = ppInputConnections[0];
    UINT32 inFrames = inConn->u32ValidFrameCount;
    UINT32 inBytes = inFrames * m_bytesPerFrame;
    UINT32 copyBytes = (inBytes < bytes) ? inBytes : bytes;
    memcpy(outConn->pBuffer, inConn->pBuffer, copyBytes);
    if (copyBytes < bytes)
    {
        memset(((BYTE*)outConn->pBuffer) + copyBytes, 0, bytes - copyBytes);
    }
}

STDMETHODIMP_(UINT32) VirtualMicApo::CalcInputFrames(UINT32 u32OutputFrames)
{
    return u32OutputFrames;
}

STDMETHODIMP_(UINT32) VirtualMicApo::CalcOutputFrames(UINT32 u32InputFrames)
{
    return u32InputFrames;
}

VirtualMicApoClassFactory::VirtualMicApoClassFactory()
    : m_refCount(1)
{
    InterlockedIncrement(&g_dllRef);
}

STDMETHODIMP VirtualMicApoClassFactory::QueryInterface(REFIID riid, void** ppv)
{
    if (!ppv) return E_POINTER;
    *ppv = nullptr;

    if (riid == __uuidof(IUnknown) || riid == __uuidof(IClassFactory))
    {
        *ppv = static_cast<IClassFactory*>(this);
        AddRef();
        return S_OK;
    }

    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) VirtualMicApoClassFactory::AddRef()
{
    return (ULONG)InterlockedIncrement(&m_refCount);
}

STDMETHODIMP_(ULONG) VirtualMicApoClassFactory::Release()
{
    ULONG ref = (ULONG)InterlockedDecrement(&m_refCount);
    if (ref == 0)
    {
        InterlockedDecrement(&g_dllRef);
        delete this;
    }
    return ref;
}

STDMETHODIMP VirtualMicApoClassFactory::CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv)
{
    if (pUnkOuter) return CLASS_E_NOAGGREGATION;
    VirtualMicApo* apo = new (std::nothrow) VirtualMicApo();
    if (!apo) return E_OUTOFMEMORY;
    HRESULT hr = apo->QueryInterface(riid, ppv);
    apo->Release();
    return hr;
}

STDMETHODIMP VirtualMicApoClassFactory::LockServer(BOOL fLock)
{
    if (fLock)
    {
        InterlockedIncrement(&g_dllRef);
    }
    else
    {
        InterlockedDecrement(&g_dllRef);
    }
    return S_OK;
}

HRESULT DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv)
{
    if (rclsid != CLSID_VirtualMicApo) return CLASS_E_CLASSNOTAVAILABLE;
    VirtualMicApoClassFactory* factory = new (std::nothrow) VirtualMicApoClassFactory();
    if (!factory) return E_OUTOFMEMORY;
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

HRESULT DllCanUnloadNow()
{
    return (g_dllRef == 0) ? S_OK : S_FALSE;
}
