## 1. Build

- [x] 1.1 `tauri.linux.conf.json`: targets `deb` and `appimage`; add `tauri.appimage.conf.json` whose `bundle.resources` is the capture helper only
- [x] 1.2 `scripts/appimage-add-backend.sh`: split runtime and squashfs at the ELF-computed offset, unpack, copy the backend into the single `usr/lib/*/resources`, repack with the original compression and block size behind the original runtime
- [x] 1.3 `scripts/build-linux.sh`: `tauri build --bundles deb`, then `tauri bundle --bundles appimage --config tauri.appimage.conf.json`, then add the backend; require `squashfs-tools`

## 2. CI

- [x] 2.1 `scripts/smoke-linux-appimage.sh`: backend identical to the build's, unpacked backend answers `/api/status`, the launched AppImage's shell starts the backend from its mount and it answers
- [x] 2.2 `build.yml`: install `squashfs-tools` and `xvfb`, run the smoke test after the Linux bundle, upload `bundle/appimage/*.AppImage` with the `.deb`
- [ ] 2.3 The Linux job passes on ubuntu-22.04

## 3. Docs

- [x] 3.1 README: Linux requirements and build output list the AppImage
- [x] 3.2 `docs/PACKAGING.md`: how the AppImage is assembled and checked, first launch (`chmod +x`, `--appimage-extract-and-run` without FUSE)
