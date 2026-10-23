#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Translate the container contract (start-node.sh) into the qualified Atlas launch profile."""
import ipaddress
import json
import os
from pathlib import Path
import re
import sys


def fabric_hcas(value, sysfs=Path('/sys/class/infiniband'), siblings=True):
    """RDMA devices for the fabric: the requested ones plus, for each, the
    active device on the same physical port behind the other PCIe domain.

    GB10 attaches its ConnectX-7 through two PCIe x4 links, so one 200G cable
    shows up as two RDMA devices (e.g. rocep1s0f0 and roceP2p1s0f0), each
    capped near 112 Gb/s. Filling the cable needs both.
    """
    names = value.split(',')
    if (not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) for name in names)
            or len(names) != len(set(names))):
        raise ValueError('FABRIC_HCA must list unique exact RDMA device names, without spaces or :port suffixes')

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

    def usable(dev):
        """An IPv4 RoCE v2 GID, which is what NCCL needs on this rail. A rail can be
        ACTIVE with no address on its netdev, and the engine then fails to initialize
        NCCL instead of running on the rail that does have one."""
        port = sysfs/dev/'ports'/'1'
        try:
            entries = sorted(port.glob('gids/*'), key=lambda g: int(g.name))
        except OSError:
            return False
        for g in entries:
            try:
                if not g.read_text().strip().startswith('0000:0000:0000:0000:0000:ffff:'):
                    continue
                kind = (port/'gid_attrs'/'types'/g.name).read_text().strip()
            except OSError:
                continue
            if 'RoCE v2' in kind:
                return True
        return False

    hcas = list(names)
    if not siblings:
        return hcas
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
                if not usable(dev):
                    print(f'fabric: skipping {dev}, no IPv4 RoCE v2 GID '
                          f'(give its netdev an address to use both rails)', file=sys.stderr)
                    continue
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


def serving_mode(environ, profile):
    """Both modes preserve the native target and use target-verified native MTP."""
    mode = environ.get('SPARKQWEN_MODE', 'strict')
    if mode not in ('strict', 'spark'):
        raise ValueError('SPARKQWEN_MODE must be strict or spark')
    required = {
        'ATLAS_QWEN4EXP_NO_PLE': '0',
        'ATLAS_MTP_DRAFTER_QSA': '0',
        'ATLAS_QSA_DISABLE': '0',
        'ATLAS_QWEN4EXP_MXFP8_DECODE': '1',
        'ATLAS_QWEN4EXP_BF16_GDN': '1',
        'ATLAS_QWEN4EXP_FP8_GDN': '0',
        'ATLAS_QWEN4EXP_PREFILL_W8A8': '1',
        'ATLAS_QWEN4EXP_PREFILL_MOE': '1',
        'ATLAS_QWEN4EXP_PREFILL_MOE_BF16': '0',
        'ATLAS_QWEN4EXP_PREFILL_BF16_PROJ': '0',
    }
    for flag, value in required.items():
        if profile['environment'].get(flag, value) != value:
            raise ValueError(f'{mode} mode requires {flag}={value}')
    if opt_ins(environ):
        raise ValueError('strict/spark modes require native FP4-Local projections; FP8_GDN is unsupported')
    args = list(profile['server_argv'])
    def single_value(flag):
        entries = [(i, arg) for i, arg in enumerate(args) if arg.split('=', 1)[0] == flag]
        if len(entries) != 1:
            raise ValueError(f'strict/spark modes require exactly one {flag}')
        index, arg = entries[0]
        if '=' in arg:
            return arg.split('=', 1)[1]
        if index + 1 < len(args) and not args[index + 1].startswith('--'):
            return args[index + 1]
        raise ValueError(f'{flag} requires a value')

    for flag, value in {'--world-size': '2', '--tp-size': '2', '--ep-size': '2',
                        '--kv-cache-dtype': 'bf16',
                        '--kernel-target': 'qwen3.8-flash-next'}.items():
        if single_value(flag) != value:
            raise ValueError(f'strict/spark modes require {flag}={value}')
    if not re.fullmatch(r'[1-9][0-9]*', single_value('--num-drafts')):
        raise ValueError('strict/spark modes require a positive --num-drafts')
    forbidden = ('--dflash', '--self-speculative', '--ngram-speculative', '--expert-tp', '--no-fast-load', '--attn-proj-dtype', '--lm-head-dtype')
    if any(arg.split('=', 1)[0] in forbidden for arg in args):
        raise ValueError('strict/spark modes support only the Qwen native MTP lane')
    if [arg for arg in args if arg.split('=', 1)[0] == '--speculative'] != ['--speculative']:
        raise ValueError('strict/spark modes require --speculative; use disable_mtp for serial requests')
    speculative_index = args.index('--speculative')
    if speculative_index + 1 < len(args) and not args[speculative_index + 1].startswith('--'):
        raise ValueError('--speculative is a flag and accepts no value')
    required.update(ATLAS_QWEN4EXP_MTP_BF16_ATTN='1' if mode == 'strict' else '0',
                    ATLAS_QWEN4EXP_DRAFT_HEAD_NVFP4='0' if mode == 'strict' else '1')
    return mode, dict(required, ATLAS_QWEN4EXP_SERVING_MODE=mode), args


def launch(environ, profile):
    mode, precision, args = serving_mode(environ, profile)
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
    siblings = environ.get('FABRIC_SIBLINGS', '0')
    if siblings not in ('0', '1'):
        raise ValueError('FABRIC_SIBLINGS must be 0 or 1')
    hcas = fabric_hcas(environ.get('FABRIC_HCA', ''), siblings=siblings == '1')
    model = environ.get('MODEL_PATH', '/models/checkpoint')
    if not Path(model).is_absolute() or any(c in model for c in '\r\n\0'):
        raise ValueError('MODEL_PATH must be an absolute path')
    # Profile values intentionally win over ambient optimization flags. Runtime
    # changes require a new reviewed image/profile instead of accidental tuning.
    # Keep the reviewed logging knobs and exact loop-recovery escape hatch,
    # as in SparkGLM. The profile still overrides these operational choices.
    env = {key: value for key, value in environ.items()
           if not key.startswith('ATLAS_') or key.startswith('ATLAS_LOG_')
           or key == 'ATLAS_LOOP_NO_SUPPRESS'}
    env.update(profile['environment'])
    env.update(precision)
    env['SPARKQWEN_MODE'] = mode
    env['NCCL_SOCKET_IFNAME'] = interface
    env['NCCL_IB_HCA'] = ','.join(hcas)
    # The engine's direct RDMA all-reduce stripes over the same devices.
    env['ATLAS_RDMA_RAILS'] = env['NCCL_IB_HCA']
    args = [str(arg).replace('${model}', model) for arg in args]
    # A dedicated pair can give the KV pool more of the unified memory than the
    # shipped default leaves free; a lower share reserves host/service memory
    # but shrinks the shared KV token pool. No context or concurrency promise.
    util = environ.get('SPARKQWEN_GPU_MEMORY_UTILIZATION')
    if util:
        if not re.fullmatch(r'0\.(7[0-9]|8[0-9]|9[0-5])', util):
            raise ValueError('SPARKQWEN_GPU_MEMORY_UTILIZATION must be 0.70 to 0.95')
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


def release_info(here):
    release = json.loads((here/'release.json').read_text())
    source_path = here/'source-manifest.json'
    if not source_path.is_file():
        source_path = here/'atlas-source.json'
    source = json.loads(source_path.read_text())
    return {'product': release['product'], 'version': release['version'],
            'engine_commit': source['commit'], 'engine_tree': source['tree']}


def print_version(here):
    info = release_info(here)
    print(f"{info['product']} {info['version']}")
    print(f"Atlas {info['engine_commit']}")
    print(f"Engine tree {info['engine_tree']}")


def main():
    here = Path(__file__).resolve().parent
    if sys.argv[1:] == ['--version']:
        print_version(here)
        return
    profile = profile_path(os.environ, here)
    argv, env = launch(os.environ, json.loads(profile.read_text()))
    model = Path(env.get('MODEL_PATH', '/models/checkpoint'))
    if not (model/'config.json').is_file() or not (model/'model.safetensors.index.json').is_file():
        raise ValueError(f'Incomplete checkpoint at {model}')
    source = json.loads((here/'source-manifest.json').read_text())
    print(json.dumps({'event': 'atlas-recipe-start', **release_info(here), 'rank': env['NODE_RANK'], 'profile': profile.stem, 'mode': env['SPARKQWEN_MODE'],
                      'opt_ins': sorted(k for k in OPT_INS if env.get(k) == '1'),
                      'source': f"{source['repository']}@{source['commit']}"}), flush=True)
    os.execve(argv[0], argv, env)


if __name__ == '__main__':
    main()
