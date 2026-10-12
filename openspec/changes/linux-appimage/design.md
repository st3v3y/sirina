## Context

The Linux bundle carries two resources: the Rust capture helper and the PyInstaller onedir backend (`resources/backend/backend` plus `_internal/`). Tauri's AppImage bundler copies resources into `AppDir/usr/lib/<product>/` and runs linuxdeploy with the GTK plugin over the whole AppDir. linuxdeploy treats every ELF it finds as something to deploy: it resolves each `DT_NEEDED`, copies dependencies into `usr/lib`, and sets rpaths. PyInstaller's `_internal/` holds wheels' vendored libraries with hashed names (`libgomp-e985bcbb.so.1.0.0`) that are found through the original wheel layout's rpaths, which PyInstaller flattens; linuxdeploy can't resolve them and aborts.

## Goals / Non-Goals

**Goals:** a working AppImage on ubuntu-22.04 CI; the backend's files bit-identical to the PyInstaller output; one build script; a CI check that the AppImage's shell starts its backend.

**Non-Goals:** signing, zsync update info, Flatpak, an arm64 AppImage.

## Decisions

### D1. Inject the backend after linuxdeploy, instead of hiding it from linuxdeploy

Alternatives considered:

- **Ship the backend as an archive resource, extracted on first launch.** linuxdeploy ignores non-ELF files, so it works, but it costs a multi-second first launch, a second copy of ~250 MB on disk, cache invalidation per version, and a code path the `.deb` doesn't need.
- **Build the whole AppImage with appimagetool from the Tauri binary and resources, skipping linuxdeploy.** The backend stays untouched, but nothing bundles WebKitGTK/GTK or sets up the GTK hooks, so the AppImage would depend on the host's WebKitGTK 4.1, which defeats the point of an AppImage.
- **Inject afterwards (chosen).** linuxdeploy does what it is good at (the Tauri binary, WebKitGTK, GTK, the helper's libpulse); the backend, which PyInstaller already made self-contained, is added unchanged.

### D2. Two Tauri passes, one compile

`tauri build --bundles deb` compiles once and makes the `.deb` with the full Linux config. `tauri bundle --bundles appimage --config tauri.appimage.conf.json` reuses that binary; the override replaces `bundle.resources` (JSON merge patch replaces arrays) with the helper alone. The binary's embedded config is irrelevant: resources are resolved at run time from the resource directory, not the config.

### D3. Repack without running the AppImage

`appimage-add-backend.sh` finds the squashfs offset from the runtime's ELF header (end of its section header table, as the runtime computes it) and checks the `hsqs` magic there. It splits the runtime and image, reads the image's compression and block size with `unsquashfs -s`, unpacks it, copies the backend into the single `usr/lib/*/resources` directory with `cp -a`, and repacks with `mksquashfs` using the same compression and block size and `-all-root`. Then it concatenates the original runtime and the new image. Reusing the runtime and its compression avoids depending on a downloaded appimagetool or runtime, and on which compressors that runtime supports. The AppImage is unsigned, so there is no embedded digest to update.

### D4. Run time

The shell resolves the resource directory as `<exe>/../lib/<product>` first (tauri-utils), which is the AppImage's mount (or the extraction directory with `--appimage-extract-and-run`). The backend runs from the read-only mount; it writes only under `APP_DATA_DIR`. Permissions are preserved by `cp -a` and `unsquashfs`, so `ensure_executable` has nothing to change on the read-only mount. The GTK hook's environment variables reach the backend but nothing there uses GTK; PyInstaller's bootloader puts its own `_internal/` first on `LD_LIBRARY_PATH`.

### D5. CI verification

`smoke-linux-appimage.sh` checks the three things that can break: the backend's bytes (`diff -r` against `frontend/src-tauri/resources/backend`), that it starts (run the unpacked `resources/backend/backend --port 8765`, poll `/api/status`), and that the shell finds it (launch the AppImage with `xvfb-run` and `dbus-run-session` under a private `XDG_DATA_HOME`, find the spawned `resources/backend/backend` process, check its executable lives under the AppImage's `.mount_` directory, read its `--port`, poll `/api/status`).

## Risks / Trade-offs

- **A bare `tauri build` on Linux fails at the AppImage step** (after writing the `.deb`). → Documented; the build script and CI pass `--bundles`.
- **Tauri changes the AppDir layout.** → The script locates `usr/lib/*/resources` and fails loudly if it isn't exactly one directory; the CI launch test catches a resolution mismatch.
- **Hosts without FUSE** can't mount the AppImage. → Documented `--appimage-extract-and-run`; tauri-utils only logs a warning there.
- **glibc floor**: the backend and the shell are built on ubuntu-22.04, so the AppImage needs glibc 2.35 or later.
