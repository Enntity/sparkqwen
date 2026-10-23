#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
cd "$HOME/qwen-common-20261022"
engine=f1fdf272cd54322ce82ad40814e19ef9915949f3
tree=f3b0524eb5925a9978d803718e721440ba323b2c
product=39f57764cfca710143615f42bf68d319cb7ad111
install=e3bb830b0c662b1a547a8c8d5aba1a37fed3c25b
GIT_LFS_SKIP_SMUDGE=1 git clone campaign-source17 campaign-source18
git -C campaign-source18 fetch ../atlas-common18.bundle HEAD
GIT_LFS_SKIP_SMUDGE=1 git -C campaign-source18 checkout --detach "$engine"
test "$(git -C campaign-source18 rev-parse HEAD 'HEAD^{tree}')" = "$(printf '%s\n%s' "$engine" "$tree")"
test -z "$(git -C campaign-source18 status --porcelain)"
GIT_LFS_SKIP_SMUDGE=1 git clone candidate-product17 candidate-product18
git -C candidate-product18 fetch ../sparkqwen-common18.bundle HEAD
GIT_LFS_SKIP_SMUDGE=1 git -C candidate-product18 checkout --detach "$product"
test "$(git -C candidate-product18 rev-parse HEAD:install)" = "$install"
mkdir build-context-18
GIT_LFS_SKIP_SMUDGE=1 git clone campaign-source18 build-context-18/engine
GIT_LFS_SKIP_SMUDGE=1 git -C build-context-18/engine checkout --detach "$engine"
git -C candidate-product18 archive HEAD install | tar -x -C build-context-18
cp build-context-18/install/dockerignore build-context-18/.dockerignore
campaign="atlas-qwen-common-campaign:${engine:0:12}"
docker build --build-arg BUILD_JOBS=8 -f campaign18.Dockerfile -t "$campaign" build-context-18 > campaign-build-18.log 2>&1
docker image inspect "$campaign" > campaign-image18.json
docker run --rm --entrypoint sha256sum "$campaign" /usr/local/bin/spark > campaign-binary18.txt
printf '%s\n' "$campaign" > campaign-image18-tag.txt
printf '%s\n' "$campaign" > campaign-image-tag.txt
printf '%s\n' "$engine" > campaign-engine-commit.txt
printf '%s\n' "$tree" > campaign-engine-tree.txt
image="ghcr.io/enntity/atlas-sparkqwen:${install:0:12}"
docker build --build-arg BUILD_JOBS=8 --build-arg INSTALL_TREE="$install" --build-arg PRODUCT_VERSION=0.2.0 -f build-context-18/install/Dockerfile -t "$image" build-context-18 > build-18.log 2>&1
docker image inspect "$image" > image-18.json
docker run --rm "$image" --version > version-image18.txt
docker run --rm --entrypoint sha256sum "$image" /usr/local/bin/spark > binary-image18.txt
printf 'BUILD18 PASSED %s %s\n' "$campaign" "$image"
