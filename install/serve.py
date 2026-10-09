#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Translate the container contract (start-node.sh) into the qualified Atlas launch profile."""
import ipaddress
import json
import os
from pathlib import Path
import re


def fabric_hcas(value, sysfs=Path('/sys/class/infiniband')):
    """RDMA devices for the fabric: the requested ones plus, for each, the
    active device on the same physical port behind the other PCIe domain.

    GB10 attaches its ConnectX-7 through two PCIe x4 links, so one 200G cable
    shows up as two RDMA devices (e.g. rocep1s0f0 and roceP2p1s0f0), each
    capped near 112 Gb/s. Filling the cable needs both.
    """
    names = value.split(',')
    if not all(re.fullmatch(r'[A-Za-z0-9_.:-]+', name) for name in names):
        raise ValueError('Invalid fabric interface or HCA')

    def pci(dev):
        try:
            return (sysfs/dev/'device').resolve().name
        except OSError:
            return None

    def active(dev):
        try:
            return 'ACTIVE' in (sysfs/dev/'ports'/'1'/'state').read_text()
        except OSError:
            return False

    hcas = list(names)
    others = sorted(p.name for p in sysfs.iterdir()) if sysfs.is_dir() else []
    for name in names:
        addr = pci(name)
        if not addr or ':' not in addr:
            continue
        slot = addr.split(':', 1)[1]
        for dev in others:
            sibling = pci(dev)
            if (dev not in hcas and sibling and ':' in sibling and sibling != addr
                    and sibling.split(':', 1)[1] == slot and active(dev)):
                hcas.append(dev)
    return hcas


# Off by default. Measured but not bit-exact against the option off; see
# docs/LIMITATIONS.md before switching it on. (QSA_TC2R, tensor-core QSA
# prefill, was the second until the engine made it the two-Spark default.)
OPT_INS = {
    # FP8 projections for the Gated DeltaNet layers (lossy: quality probe 40/40
    # and 12/12 on our pair, but outputs differ from BF16).
    'SPARKQWEN_FP8_GDN': {'ATLAS_QWEN4EXP_FP8_GDN': '1'},
}


def opt_ins(environ):
    env = {}
    for switch, flags in OPT_INS.items():
        value = environ.get(switch, '0')
        if value not in ('0', '1'):
            raise ValueError(f'{switch} must be 0 or 1')
        if value == '1':
            env.update(flags)
    return env


def launch(environ, profile):
    rank = environ.get('NODE_RANK', '')
    if rank not in ('0', '1'):
        raise ValueError('NODE_RANK must be 0 or 1')
    master = str(ipaddress.ip_address(environ['MASTER_ADDR']))
    port = int(environ.get('MASTER_PORT', '29510'))
    if not 1 <= port <= 65535:
        raise ValueError('Invalid MASTER_PORT')
    interface = environ['FABRIC_INTERFACE']
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', interface):
        raise ValueError('Invalid fabric interface or HCA')
    hcas = fabric_hcas(environ.get('FABRIC_HCA', 'rocep1s0f0'))
    model = environ.get('MODEL_PATH', '/models/checkpoint')
    if not Path(model).is_absolute() or any(c in model for c in '\r\n\0'):
        raise ValueError('MODEL_PATH must be an absolute path')
    # Profile values intentionally win over ambient optimization flags. Runtime
    # changes require a new reviewed image/profile instead of accidental tuning.
    env = {key: value for key, value in environ.items() if not key.startswith('ATLAS_')}
    env.update(profile['environment'])
    env.update(opt_ins(environ))
    env['NCCL_SOCKET_IFNAME'] = interface
    env['NCCL_IB_HCA'] = ','.join(hcas)
    # The engine's direct RDMA all-reduce stripes over the same devices.
    env['ATLAS_RDMA_RAILS'] = env['NCCL_IB_HCA']
    args = [str(arg).replace('${model}', model) for arg in profile['server_argv']]
    # A dedicated pair can give the KV pool more of the unified memory than the
    # shipped default leaves free.
    util = environ.get('SPARKQWEN_GPU_MEMORY_UTILIZATION')
    if util:
        if not re.fullmatch(r'0\.(8[0-9]|9[0-5])', util):
            raise ValueError('SPARKQWEN_GPU_MEMORY_UTILIZATION must be 0.80 to 0.95')
        args = [f'--gpu-memory-utilization={util}' if a.startswith('--gpu-memory-utilization=') else a
                for a in args]
    name = environ.get('SERVED_MODEL_NAME', 'qwen3.8-flash-next-atlas')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', name):
        raise ValueError('Invalid SERVED_MODEL_NAME')
    args += [f'--rank={rank}', f'--master-addr={master}', f'--master-port={port}',
             '--bind=127.0.0.1', f'--port={8893 + int(rank)}', f'--model-name={name}']
    return ['/usr/local/bin/spark', *args], env


def profile_path(environ, here):
    """The launch profile named by SPARKQWEN_PROFILE (default 8x32k)."""
    name = environ.get('SPARKQWEN_PROFILE', '8x32k')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name):
        raise ValueError('Invalid SPARKQWEN_PROFILE')
    return here/'profiles'/f'{name}.json'


def main():
    here = Path(__file__).resolve().parent
    profile = profile_path(os.environ, here)
    argv, env = launch(os.environ, json.loads(profile.read_text()))
    model = Path(env.get('MODEL_PATH', '/models/checkpoint'))
    if not (model/'config.json').is_file() or not (model/'model.safetensors.index.json').is_file():
        raise ValueError(f'Incomplete checkpoint at {model}')
    source = json.loads((here/'source-manifest.json').read_text())
    print(json.dumps({'event': 'atlas-recipe-start', 'rank': env['NODE_RANK'], 'profile': profile.stem,
                      'opt_ins': sorted(k for k in OPT_INS if env.get(k) == '1'),
                      'source': f"{source['repository']}@{source['commit']}"}), flush=True)
    os.execve(argv[0], argv, env)


if __name__ == '__main__':
    main()
