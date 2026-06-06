#include "AudioDeviceManager.h"

#include <Functiondiscoverykeys_devpkey.h>
#include <propvarutil.h>

#include <stdexcept>

namespace {

std::wstring FlowLabel(EDataFlow flow) {
    switch (flow) {
    case eRender:
        return L"render";
    case eCapture:
        return L"capture";
    default:
        return L"unknown";
    }
}

std::wstring StateLabel(DWORD state) {
    switch (state) {
    case DEVICE_STATE_ACTIVE:
        return L"active";
    case DEVICE_STATE_DISABLED:
        return L"disabled";
    case DEVICE_STATE_NOTPRESENT:
        return L"not-present";
    case DEVICE_STATE_UNPLUGGED:
        return L"unplugged";
    default:
        return L"unknown";
    }
}

std::runtime_error HResultError(const char* action, HRESULT hr) {
    return std::runtime_error(std::string(action) + " failed with HRESULT 0x" + std::to_string(static_cast<unsigned long>(hr)));
}

std::wstring ReadFriendlyName(IPropertyStore* properties) {
    PROPVARIANT value;
    PropVariantInit(&value);
    const HRESULT hr = properties->GetValue(PKEY_Device_FriendlyName, &value);
    if (FAILED(hr)) {
        PropVariantClear(&value);
        return L"(unknown)";
    }

    std::wstring result = value.vt == VT_LPWSTR && value.pwszVal != nullptr ? value.pwszVal : L"(unknown)";
    PropVariantClear(&value);
    return result;
}

} // namespace

AudioDeviceManager::AudioDeviceManager() : enumerator_(nullptr) {
    const HRESULT hr = CoCreateInstance(
        __uuidof(MMDeviceEnumerator),
        nullptr,
        CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator),
        reinterpret_cast<void**>(&enumerator_));
    if (FAILED(hr) || enumerator_ == nullptr) {
        throw HResultError("CoCreateInstance(MMDeviceEnumerator)", hr);
    }
}

AudioDeviceManager::~AudioDeviceManager() {
    if (enumerator_ != nullptr) {
        enumerator_->Release();
        enumerator_ = nullptr;
    }
}

std::vector<AudioEndpointInfo> AudioDeviceManager::Enumerate(EDataFlow flow) const {
    IMMDeviceCollection* collection = nullptr;
    const HRESULT hr = enumerator_->EnumAudioEndpoints(flow, DEVICE_STATEMASK_ALL, &collection);
    if (FAILED(hr) || collection == nullptr) {
        throw HResultError("EnumAudioEndpoints", hr);
    }

    UINT count = 0;
    collection->GetCount(&count);

    std::vector<AudioEndpointInfo> endpoints;
    endpoints.reserve(count);
    for (UINT index = 0; index < count; ++index) {
        IMMDevice* device = nullptr;
        if (SUCCEEDED(collection->Item(index, &device)) && device != nullptr) {
            endpoints.push_back(ReadEndpoint(device, flow));
            device->Release();
        }
    }

    collection->Release();
    return endpoints;
}

AudioEndpointInfo AudioDeviceManager::GetDefault(EDataFlow flow, ERole role) const {
    IMMDevice* device = nullptr;
    const HRESULT hr = enumerator_->GetDefaultAudioEndpoint(flow, role, &device);
    if (FAILED(hr) || device == nullptr) {
        throw HResultError("GetDefaultAudioEndpoint", hr);
    }

    AudioEndpointInfo info = ReadEndpoint(device, flow);
    device->Release();
    return info;
}

AudioEndpointInfo AudioDeviceManager::ReadEndpoint(IMMDevice* device, EDataFlow flow) const {
    LPWSTR rawId = nullptr;
    HRESULT hr = device->GetId(&rawId);
    if (FAILED(hr) || rawId == nullptr) {
        throw HResultError("IMMDevice::GetId", hr);
    }

    DWORD state = 0;
    hr = device->GetState(&state);
    if (FAILED(hr)) {
        CoTaskMemFree(rawId);
        throw HResultError("IMMDevice::GetState", hr);
    }

    IPropertyStore* properties = nullptr;
    hr = device->OpenPropertyStore(STGM_READ, &properties);
    if (FAILED(hr) || properties == nullptr) {
        CoTaskMemFree(rawId);
        throw HResultError("IMMDevice::OpenPropertyStore", hr);
    }

    AudioEndpointInfo info;
    info.id = rawId;
    info.name = ReadFriendlyName(properties);
    info.flow = FlowLabel(flow);
    info.state = StateLabel(state);

    properties->Release();
    CoTaskMemFree(rawId);
    return info;
}
