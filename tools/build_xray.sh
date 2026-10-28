#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
source_dir="$root/.xray-source"
expected=76a6e2172210613fcb4aa32b6de55bcd9452ce43
[[ -d "$source_dir/.git" ]] || { echo 'Check out 2dust/AndroidLibXrayLite at the pinned commit into .xray-source' >&2; exit 1; }
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$expected" ]] || { echo 'Unexpected Xray engine revision' >&2; exit 1; }
python3 "$root/tools/prepare_xray_compat.py" --source "$source_dir"
: "${ANDROID_HOME:?Set ANDROID_HOME}"
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --install 'ndk;29.0.14206865'
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/29.0.14206865"
cd "$source_dir"
mobile_version="$(go list -m -f '{{.Version}}' golang.org/x/mobile)"
go install "golang.org/x/mobile/cmd/gomobile@$mobile_version"
go install "golang.org/x/mobile/cmd/gobind@$mobile_version"
export PATH="$(go env GOPATH)/bin:$PATH"
gomobile init
gomobile bind -target=android/arm,android/arm64,android/amd64 -androidapi 26 -trimpath -ldflags='-s -w -buildid= -checklinkname=0' -o libv2ray.aar ./
mkdir -p "$root/android/app/libs"
cp libv2ray.aar "$root/android/app/libs/"

