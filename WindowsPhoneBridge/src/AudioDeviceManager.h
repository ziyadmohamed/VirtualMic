#pragma once

#include <mmdeviceapi.h>

#include <string>
#include <vector>

struct AudioEndpointInfo {
    std::wstring id;
    std::wstring name;
    std::wstring flow;
    std::wstring state;
};

class AudioDeviceManager {
public:
    AudioDeviceManager();
    ~AudioDeviceManager();

    std::vector<AudioEndpointInfo> Enumerate(EDataFlow flow) const;
    AudioEndpointInfo GetDefault(EDataFlow flow, ERole role) const;

private:
    IMMDeviceEnumerator* enumerator_;

    AudioEndpointInfo ReadEndpoint(IMMDevice* device, EDataFlow flow) const;
};
