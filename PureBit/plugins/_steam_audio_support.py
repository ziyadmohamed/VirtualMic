import os


STEAMAUDIO_VERSION_TEXT = "4.8.1"
STEAMAUDIO_VERSION = (4 << 16) | (8 << 8) | 1

_SHARED_DLL = None
_SHARED_CONTEXT = None


def _app_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _candidate_roots():
    app_root = _app_root()
    env_root = os.environ.get("STEAMAUDIO_ROOT")
    candidates = []

    if env_root:
        candidates.append((env_root, "STEAMAUDIO_ROOT"))

    candidates.extend(
        [
            (os.path.join(app_root, "third_party", "steamaudio"), "package third_party"),
            (os.path.join(app_root, "steamaudio"), "package root"),
            (os.path.join(app_root, "vendor", "steamaudio"), "package vendor"),
            (os.path.join(app_root, "third_party", f"steamaudio_{STEAMAUDIO_VERSION_TEXT}", "steamaudio"), "package versioned third_party"),
            (os.path.join(app_root, f"steamaudio_{STEAMAUDIO_VERSION_TEXT}", "steamaudio"), "package versioned root"),
        ]
    )

    return [(os.path.abspath(root), source) for root, source in candidates]


def resolve_steam_audio_paths():
    for root, source in _candidate_roots():
        dll_path = os.path.join(root, "lib", "windows-x64", "phonon.dll")
        if os.path.exists(dll_path):
            return {
                "root": root,
                "dll": os.path.abspath(dll_path),
                "source": source,
            }

    default_root, default_source = _candidate_roots()[0]
    return {
        "root": default_root,
        "dll": os.path.join(default_root, "lib", "windows-x64", "phonon.dll"),
        "source": default_source,
    }
