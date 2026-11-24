#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
build="${BUILD_DIR:-$root/native/build-n4eac-macos}"
stage="${STAGE_DIR:-$root/dist/n4eac-macos}"
qt="$(brew --prefix qtbase)"
cmake -S "$root/native" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_DEPLOYMENT_TARGET=27.0 \
    -DCMAKE_PREFIX_PATH="$qt" \
    -DQT_ADDITIONAL_PACKAGES_PREFIX_PATH="$(brew --prefix qtwebsockets);$(brew --prefix qtsvg)" \
    -DDATA2G_PROFILE=hf -DDATA2G_BUILD_HOST=ON -DDATA2G_BUILD_GUI=ON \
    -DDATA2G_BUILD_TESTS=ON -DDATA2G_BUILD_PYMODULE=OFF -DDATA2G_BUILD_QTAUDIO=ON \
    -DDATA2G_AUDIO_BACKEND=miniaudio -DDATA2G_BUILD_RIG=ON -DDATA2G_HAMLIB_SYSTEM=ON
cmake --build "$build" --parallel "${JOBS:-6}"
QT_PLUGIN_PATH="$qt/share/qt/plugins" ctest --test-dir "$build" --parallel 4 --timeout 240 --output-on-failure
python3 "$root/tools/macos/package.py" --build "$build" --stage "$stage"
