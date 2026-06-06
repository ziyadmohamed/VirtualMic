#include "AudioDeviceManager.h"

#include <objbase.h>

#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct ComApartment {
    ComApartment() {
        const HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
        if (FAILED(hr)) {
            throw std::runtime_error("CoInitializeEx failed");
        }
    }

    ~ComApartment() {
        CoUninitialize();
    }
};

void PrintUsage() {
    std::wcout
        << L"phone_bridge_ctl usage:\n"
        << L"  phone_bridge_ctl list\n"
        << L"  phone_bridge_ctl defaults\n"
        << L"\n"
        << L"Purpose:\n"
        << L"  Inspect Windows audio endpoints relevant to a future Phone Link-style\n"
        << L"  communications bridge. This is the native Windows control path start.\n";
}

void PrintEndpoint(const AudioEndpointInfo& endpoint) {
    std::wcout << L"- " << endpoint.name << L"\n";
    std::wcout << L"  flow:  " << endpoint.flow << L"\n";
    std::wcout << L"  state: " << endpoint.state << L"\n";
    std::wcout << L"  id:    " << endpoint.id << L"\n";
}

void PrintDefaults(AudioDeviceManager& manager) {
    std::wcout << L"Default render communications:\n";
    PrintEndpoint(manager.GetDefault(eRender, eCommunications));
    std::wcout << L"\nDefault capture communications:\n";
    PrintEndpoint(manager.GetDefault(eCapture, eCommunications));
    std::wcout << L"\nDefault render multimedia:\n";
    PrintEndpoint(manager.GetDefault(eRender, eMultimedia));
    std::wcout << L"\nDefault capture multimedia:\n";
    PrintEndpoint(manager.GetDefault(eCapture, eMultimedia));
}

void PrintList(AudioDeviceManager& manager) {
    std::wcout << L"Render endpoints:\n";
    for (const auto& endpoint : manager.Enumerate(eRender)) {
        PrintEndpoint(endpoint);
    }

    std::wcout << L"\nCapture endpoints:\n";
    for (const auto& endpoint : manager.Enumerate(eCapture)) {
        PrintEndpoint(endpoint);
    }
}

} // namespace

int wmain(int argc, wchar_t* argv[]) {
    try {
        if (argc < 2) {
            PrintUsage();
            return 1;
        }

        const std::wstring command = argv[1];
        ComApartment apartment;
        AudioDeviceManager manager;

        if (command == L"list") {
            PrintList(manager);
            return 0;
        }

        if (command == L"defaults") {
            PrintDefaults(manager);
            return 0;
        }

        PrintUsage();
        return 1;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }
}
