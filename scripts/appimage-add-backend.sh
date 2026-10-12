#!/usr/bin/env bash
# Add the frozen backend to a Tauri-built AppImage without running linuxdeploy over it.
#
# Tauri's AppImage step runs linuxdeploy over every ELF file in the AppDir. It can't resolve
# the PyInstaller backend's vendored libraries (ctranslate2's libgomp-<hash>.so) and would
# rewrite their rpaths. So build-linux.sh bundles the AppImage without the backend
# (tauri.appimage.conf.json), and this script copies it in afterwards, byte for byte:
# unpack the AppImage's squashfs, add <resources>/resources/backend, and repack it behind
# the same runtime with the same compression.
#
# Usage: appimage-add-backend.sh <Sirina.AppImage> <backend onedir>
# Needs squashfs-tools (mksquashfs, unsquashfs). Doesn't run the AppImage, so no FUSE.
set -euo pipefail

[ $# -eq 2 ] || { echo "usage: $0 <Sirina.AppImage> <backend onedir>" >&2; exit 2; }
APPIMAGE="$(realpath "$1")"
BACKEND="$(realpath "$2")"
[ -x "$BACKEND/backend" ] || { echo "no executable $BACKEND/backend" >&2; exit 1; }
for tool in mksquashfs unsquashfs; do
  command -v "$tool" >/dev/null || { echo "$tool not found — apt install squashfs-tools" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# An AppImage is an ELF runtime followed by a squashfs image. The runtime's size is where
# its section header table ends (what the runtime itself computes); 64-bit little-endian.
read -r shoff < <(od -An -t u8 -j 40 -N 8 "$APPIMAGE")
read -r shentsize shnum < <(od -An -t u2 -j 58 -N 4 "$APPIMAGE")
OFFSET=$((shoff + shentsize * shnum))
if [ "$(od -An -c -j "$OFFSET" -N 4 "$APPIMAGE" | tr -d ' ')" != "hsqs" ]; then
  echo "no squashfs image at offset $OFFSET of $APPIMAGE" >&2
  exit 1
fi

head -c "$OFFSET" "$APPIMAGE" >"$WORK/runtime"
tail -c +$((OFFSET + 1)) "$APPIMAGE" >"$WORK/image.squashfs"
INFO="$(unsquashfs -s "$WORK/image.squashfs")"
COMP="$(sed -n 's/^Compression //p' <<<"$INFO")"
BLOCK="$(sed -n 's/^Block size //p' <<<"$INFO")"
unsquashfs -no-progress -d "$WORK/root" "$WORK/image.squashfs" >/dev/null

# Resources live in usr/lib/<product name>/; the config lists them under resources/.
mapfile -t dirs < <(find "$WORK/root/usr/lib" -mindepth 2 -maxdepth 2 -type d -name resources)
[ "${#dirs[@]}" -eq 1 ] || { echo "expected one usr/lib/*/resources in the AppImage, found ${#dirs[@]}" >&2; exit 1; }
DEST="${dirs[0]}/backend"
[ ! -e "$DEST" ] || { echo "the AppImage already has ${DEST#"$WORK/root/"}" >&2; exit 1; }
cp -a "$BACKEND" "$DEST"
echo "==> Added the backend at ${DEST#"$WORK/root/"} ($(du -sh "$DEST" | cut -f1))"

mksquashfs "$WORK/root" "$WORK/new.squashfs" -comp "$COMP" -b "$BLOCK" \
  -all-root -noappend -no-xattrs -no-progress >/dev/null
cat "$WORK/runtime" "$WORK/new.squashfs" >"$WORK/out.AppImage"
chmod 755 "$WORK/out.AppImage"
mv "$WORK/out.AppImage" "$APPIMAGE"
echo "==> Repacked $APPIMAGE ($COMP, $(du -h "$APPIMAGE" | cut -f1))"
