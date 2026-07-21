#!/bin/sh
# Render icon-1024.png to sidelinehd.icns (M5 slice 68a).
#
# Dev-time tool, run by hand after replacing the artwork — never by the
# build or CI, which consume the committed .icns. Uses only sips and
# iconutil, both shipped with macOS. Byte-identity across sips versions is
# not required; the committed .icns is the artifact of record.
#
#   sh packaging/icon/make-icns.sh

set -eu

here="$(cd "$(dirname "$0")" && pwd)"
source_png="$here/icon-1024.png"
iconset="$here/sidelinehd.iconset"
output="$here/sidelinehd.icns"

[ -f "$source_png" ] || { echo "missing $source_png" >&2; exit 1; }

rm -rf "$iconset"
mkdir "$iconset"

for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$source_png" \
        --out "$iconset/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$source_png" \
        --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$iconset" -o "$output"
rm -rf "$iconset"
echo "wrote $output"
