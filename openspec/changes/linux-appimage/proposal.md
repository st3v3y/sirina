## Why

Linux ships only as a `.deb` (`cross-platform-recording`), so only Debian and Ubuntu users can install Sirina. The AppImage was dropped because Tauri's AppImage step runs linuxdeploy over every ELF file in the AppDir, including the PyInstaller backend's `_internal/` libraries. On ubuntu-22.04 it failed with `Could not find dependency: libgomp-e985bcbb.so.1.0.0` (ctranslate2's vendored libgomp), and had it succeeded it would have rewritten the backend libraries' rpaths.

## What Changes

- **Linux ships an AppImage again**, next to the `.deb`, built so the frozen backend never goes through linuxdeploy:
  - `tauri build --bundles deb` builds the app and the `.deb` with every resource, as today.
  - `tauri bundle --bundles appimage --config tauri.appimage.conf.json` bundles the same binary as an AppImage whose only resource is the capture helper; linuxdeploy bundles WebKitGTK, GTK and libpulse as usual.
  - `scripts/appimage-add-backend.sh` unpacks the AppImage's squashfs, copies the backend to `usr/lib/<product>/resources/backend/` byte for byte, and repacks it behind the same runtime with the same compression.
- `tauri.linux.conf.json` lists both `deb` and `appimage` targets; `build-linux.sh` runs the three steps and needs `squashfs-tools`.
- **CI smoke test** (`scripts/smoke-linux-appimage.sh`, ubuntu-22.04): unpack the AppImage, check the bundled backend is identical to the build's, start it and wait for `/api/status`, then launch the AppImage under Xvfb and check the shell started the backend from the AppImage's mount and that it answers. The AppImage is uploaded with the `.deb` as a run artifact.
- README and `docs/PACKAGING.md`: AppImage build output, how it is assembled, and first-launch steps (`chmod +x`, `--appimage-extract-and-run` without FUSE).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `desktop-app`: the Linux distribution is an AppImage and a `.deb`, and the unsigned-distribution steps cover running the AppImage. (Builds on the requirement text from `cross-platform-recording`, which must be archived first.)

## Impact

- Code: none in the app; the shell already resolves resources from `<exe>/../lib/<product>`, which is the AppImage's mount.
- Build: `scripts/build-linux.sh`, new `scripts/appimage-add-backend.sh` and `scripts/smoke-linux-appimage.sh`, new `frontend/src-tauri/tauri.appimage.conf.json`, `frontend/src-tauri/tauri.linux.conf.json`, `.github/workflows/build.yml` (adds `squashfs-tools` and `xvfb`).
- A bare `tauri build` on Linux now fails at the AppImage step (after the `.deb`); builds go through the script.
