# SPDX-License-Identifier: AGPL-3.0-only
# Context: build.sh's pinned Enntity/atlas engine checkout and packaged install assets.
# Adapted from SparkGLM's image. Qwen3.8-Flash-Next loads NVIDIA's checkpoint
# directly, so there is no converter and no native bridge stage.
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04@sha256:1e8ac7a54c184a1af8ef2167f28fa98281892a835c981ebcddb1fad04bdd452d AS builder
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends --allow-change-held-packages \
    git ca-certificates build-essential python3 curl pkg-config cmake libclang-dev \
    libibverbs-dev librdmacm-dev libnccl2=2.31.2-1+cuda13.3 libnccl-dev=2.31.2-1+cuda13.3 && \
    rm -rf /var/lib/apt/lists/*
# rustup-init at a pinned release, checked against its published SHA-256
# before it runs (the image is arm64 only).
ARG RUSTUP_VERSION=1.29.1
ARG RUSTUP_SHA256=15f6e4ce9f583b929c996c91562bad6d4454f3281de858b02cdfdef615fac433
RUN curl --proto '=https' --tlsv1.2 -sSfLo /tmp/rustup-init \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/aarch64-unknown-linux-gnu/rustup-init" && \
    echo "${RUSTUP_SHA256}  /tmp/rustup-init" | sha256sum -c - && chmod +x /tmp/rustup-init && \
    /tmp/rustup-init -y --profile minimal --default-toolchain 1.93.1 && rm /tmp/rustup-init
ENV PATH="/root/.cargo/bin:${PATH}"
ENV RUSTUP_TOOLCHAIN=1.93.1 CUDA_HOME=/usr/local/cuda CUTLASS_HOME=/opt/cutlass
ENV LIBRARY_PATH=/usr/local/cuda/lib64/stubs
RUN git clone https://github.com/NVIDIA/cutlass.git /opt/cutlass && \
    git -C /opt/cutlass checkout cf064d2e6bad2886238ac565b3b49007764f4939
WORKDIR /build
COPY engine/Cargo.toml engine/Cargo.lock engine/rust-toolchain.toml engine/README.md ./
COPY engine/crates/ crates/
COPY engine/kernels/ kernels/
COPY engine/vendor/ vendor/
COPY engine/jinja-templates/ jinja-templates/
COPY engine/tests/fixtures/ tests/fixtures/
# The build-time tests compile every atlas-core test module, which include_str! these.
COPY engine/test_data/ test_data/
ENV ATLAS_TARGET_HW=gb10 ATLAS_TARGET_MODEL=qwen3.8-flash-next ATLAS_TARGET_QUANT=nvfp4
ARG BUILD_JOBS=4
# BuildKit cache mount for the cargo target directory, so iterating on the
# engine does not recompile every kernel. Every cargo step mounts the same
# cache, and the binary is copied out because mounted paths never reach a layer.
RUN --mount=type=cache,target=/build/target,id=atlas-cargo-target-sparkqwen,sharing=shared \
    cargo build --locked --release -j "$BUILD_JOBS" -p spark-server && \
    install -D target/release/spark /build/dist/spark
# License notices of every third-party crate compiled into the binary.
COPY install/rust-notices.py /product/install/rust-notices.py
RUN python3 /product/install/rust-notices.py /build /build/dist/notices-rust
# CUDA stubs permit these CPU-only tests without GPU build entitlements.
RUN mkdir -p /opt/cuda-stubs && \
    ln -s /usr/local/cuda/lib64/stubs/libcuda.so /opt/cuda-stubs/libcuda.so.1
# The published Qwen3.8-Flash-Next config parses into the hybrid MoE layout the
# kernels were built for; then the serving lifecycle, admission, cancellation
# and tool-parser tests on the same Linux/CUDA build as the shipped binary.
# Each filter must match at least one test.
RUN --mount=type=cache,target=/build/target,id=atlas-cargo-target-sparkqwen,sharing=shared \
    set -eu; for check in atlas-core:qwen4_exp_ spark-server:scheduler::lifecycle_tests \
        spark-server:scheduler::admission:: spark-server:cancellation_tests \
        spark-server:disconnect_prefill_tests spark-server:buffered_disconnect_ spark-server:tool_parser::; do \
      crate=${check%%:*}; filter=${check#*:}; \
      if [ "$crate" = spark-server ]; then target="--bin spark"; else target="--lib"; fi; \
      LD_LIBRARY_PATH=/opt/cuda-stubs:/usr/local/cuda/lib64 \
      timeout --signal=TERM --kill-after=10s 600 \
      cargo test --locked --release -j "$BUILD_JOBS" -p "$crate" $target "$filter" \
        > /tmp/atlas-check.log 2>&1 || { cat /tmp/atlas-check.log; exit 1; }; \
      cat /tmp/atlas-check.log; \
      grep -E 'test result: ok. [1-9][0-9]* passed;' /tmp/atlas-check.log; \
    done

FROM nvidia/cuda:13.0.0-runtime-ubuntu24.04@sha256:95318efecfd68ab3d109da5277863257b06137c84f34a87f38de970d5cd035d3
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends --allow-change-held-packages \
    python3 ca-certificates libnccl2=2.31.2-1+cuda13.3 libibverbs1 librdmacm1 \
    ibverbs-providers libnl-3-200 libnl-route-3-200 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /build/dist/spark /usr/local/bin/spark
COPY --from=builder /build/jinja-templates/ /jinja-templates/
COPY --from=builder /opt/cutlass/LICENSE.txt /opt/atlas/notices/CUTLASS-LICENSE.txt
COPY --from=builder /build/dist/notices-rust/ /opt/atlas/notices/rust/
COPY install/serve.py /opt/atlas/
COPY install/profiles/ /opt/atlas/profiles/
COPY install/atlas-source.json /opt/atlas/source-manifest.json
COPY install/checkpoint.json /opt/atlas/checkpoint.json
COPY engine/LICENSE /LICENSE
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64
ENV RUST_LOG=info
EXPOSE 8893
# The image's identity is the git tree of install/ (its tag); label it last.
ARG INSTALL_TREE
RUN test -n "$INSTALL_TREE"
LABEL org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/Enntity/sparkqwen" \
      io.enntity.sparkqwen.install-tree="$INSTALL_TREE"
ENTRYPOINT ["python3", "/opt/atlas/serve.py"]
