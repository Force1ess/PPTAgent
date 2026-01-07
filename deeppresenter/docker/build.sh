SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE="node:lts-bullseye-slim"
TARGET_IMAGE="desktop-commander-deeppresenter"

PULL_OPT=""
docker image inspect "$BASE_IMAGE" &>/dev/null && PULL_OPT="--pull=false"

docker build "$SCRIPT_DIR" -t "$TARGET_IMAGE" $PULL_OPT \
    --build-arg http_proxy="$http_proxy" \
    --build-arg https_proxy="$https_proxy" \
    --build-arg no_proxy="$no_proxy"
