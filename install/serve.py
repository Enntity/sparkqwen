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


def disk_prefix_cache(gb, mode):
    """Engine settings that keep evicted prefix-cache blocks and Gated DeltaNet
    state snapshots on the node's disk, in the directory start-node.sh mounts
    at /prefix-cache, one subdirectory per mode. The size (GiB per node) is
    split evenly between the two; empty or 0 leaves the tier off. Same engine
    tier and settings as SparkGLM."""
    if gb in ('', '0'):
        return {}
    if not re.fullmatch(r'[1-9][0-9]{1,2}', gb) or not 16 <= int(gb) <= 100:
        raise ValueError('SPARKQWEN_PREFIX_CACHE_GB must be a whole number from 16 to 100')
    kv = int(gb) // 2
    return {'ATLAS_KV_NVME_DIR': f'/prefix-cache/{mode}/kv', 'ATLAS_KV_NVME_GB': str(kv),
            'ATLAS_GLM_NVME_FAST': '1', 'ATLAS_SSM_TIER': '1', 'ATLAS_SSM_TIER_UNIFIED': '1',
            'ATLAS_SSM_TIER_SWAP_DIR': f'/prefix-cache/{mode}/ssm', 'ATLAS_SSM_TIER_DISK_GB': str(int(gb) - kv),
            'ATLAS_SSM_TIER_SLOTS': '2'}


def serving_mode(environ, profile):
    """Both modes preserve the native target and use target-verified native MTP."""
    mode = environ.get('SPARKQWEN_MODE', 'spark')
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
        'ATLAS_QWEN4EXP_MXFP8_SHARED': '1',
        'ATLAS_QWEN4EXP_PREFILL_W4A4': '1',
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


def tool_guard_args(environ, profile_args):
    """Operator policy is explicit and independent of model/performance profiles."""
    if any(arg.split('=', 1)[0].startswith('--tool-guard') for arg in profile_args):
        raise ValueError('Configure the tool guard with SPARKQWEN_TOOL_GUARD variables, not profile arguments')
    mode = environ.get('SPARKQWEN_TOOL_GUARD', 'on')
    if mode not in ('on', 'off'):
        raise ValueError('SPARKQWEN_TOOL_GUARD must be on or off')
    limit = environ.get('SPARKQWEN_TOOL_GUARD_MAX_BYTES', '1048576')
    if not re.fullmatch(r'[1-9][0-9]{0,7}', limit) or int(limit) > 67108864:
        raise ValueError('SPARKQWEN_TOOL_GUARD_MAX_BYTES must be 1 to 67108864')
    result = [f'--tool-guard={mode}', f'--tool-guard-max-bytes={limit}']
    for action in ('ALLOW', 'DENY'):
        value = environ.get(f'SPARKQWEN_TOOL_GUARD_{action}_HOSTS', '')
        for host in value.split(',') if value else []:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*|\[[A-Fa-f0-9:.]+\]', host):
                raise ValueError(f'SPARKQWEN_TOOL_GUARD_{action}_HOSTS requires comma-separated exact hosts, without schemes, ports or wildcards')
            result.append(f'--tool-guard-{action.lower()}-host={host}')
    return result


SINGLE_MODEL = 'qwen3.8-27b'


def _flag_values(args, flag):
    return [a.split('=', 1)[1] if '=' in a else None for a in args if a.split('=', 1)[0] == flag]


def _engine_env(environ, profile):
    # Profile values win over ambient optimization flags; only the reviewed
    # logging knobs and the loop-recovery escape hatch pass through.
    env = {key: value for key, value in environ.items()
           if not key.startswith('ATLAS_') or key.startswith('ATLAS_LOG_')
           or key == 'ATLAS_LOOP_NO_SUPPRESS'}
    env.update(profile['environment'])
    return env


def _memory_share(environ, args, low=7):
    """The SPARKQWEN_GPU_MEMORY_UTILIZATION override, 0.{low}0 to 0.95: the
    pair's floor is 0.70; the 27B's saver profile runs at 0.59, so its floor is 0.40."""
    util = environ.get('SPARKQWEN_GPU_MEMORY_UTILIZATION')
    if not util:
        return args
    if not re.fullmatch(r'0\.([0-8][0-9]|9[0-5])', util) or int(util[2]) < low:
        raise ValueError(f'SPARKQWEN_GPU_MEMORY_UTILIZATION must be 0.{low}0 to 0.95')
    return [f'--gpu-memory-utilization={util}' if a.startswith('--gpu-memory-utilization=') else a for a in args]


# The 27B drafter choice (SPARKQWEN_DRAFTER): the profile's DFlash2 drafter,
# Tencent's DSpine drafter (16-row blocks) in its place, or both, each request
# routed between them by the engine (--draft-model-alt).
DRAFTERS = ('dflash2', 'dspine', 'both')
DSPINE_GAMMA = '16'


def _with_drafter(args, drafter):
    """The profile's argv (DFlash2 at its gamma) for `drafter`."""
    if drafter == 'dflash2':
        return args
    out = []
    for a in args:
        if a == '--draft-model=${draft}':
            out.append('--draft-model=${dspine}' if drafter == 'dspine' else a)
            if drafter == 'both':
                out.append('--draft-model-alt=${dspine}')
        elif a.startswith('--dflash-gamma='):
            out.append('--dflash-gamma=' + DSPINE_GAMMA)
        else:
            out.append(a)
    return out


def launch_single(environ, profile):
    """Qwen3.8-27B on one Spark: one engine process, no ranks, no fabric."""
    args = list(profile['server_argv'])
    if _flag_values(args, '--kernel-target') != [SINGLE_MODEL]:
        raise ValueError(f'the 27B profile requires --kernel-target={SINGLE_MODEL}')
    for flag in ('--world-size', '--tp-size', '--ep-size', '--rank', '--master-addr'):
        if _flag_values(args, flag):
            raise ValueError(f'the 27B profile runs on one Spark; {flag} is not allowed')
    if '--dflash' not in args or _flag_values(args, '--draft-model') != ['${draft}'] or \
            not re.fullmatch(r'[1-9][0-9]*', (_flag_values(args, '--dflash-gamma') or [''])[0] or ''):
        raise ValueError('the 27B profile requires --dflash, --draft-model=${draft} and a positive --dflash-gamma')
    # The profile names its drafter (27b-max: both); SPARKQWEN_DRAFTER overrides.
    drafter = environ.get('SPARKQWEN_DRAFTER') or profile.get('drafter') or 'dflash2'
    if drafter not in DRAFTERS:
        raise ValueError(f'SPARKQWEN_DRAFTER must be one of {", ".join(DRAFTERS)}')
    args = _with_drafter(args, drafter)
    paths = {}
    keys = [('MODEL_PATH', '/models/checkpoint'), ('DRAFT_PATH', None)]
    if drafter != 'dflash2':
        keys.append(('DSPINE_PATH', None))
    for key, default in keys:
        path = environ.get(key, default) or ''
        if not Path(path).is_absolute() or any(c in path for c in '\r\n\0'):
            raise ValueError(f'{key} must be an absolute path')
        paths[key] = path
    env = _engine_env(environ, profile)
    env['SPARKQWEN_MODE'] = 'single'
    args = _memory_share(environ, [str(a).replace('${model}', paths['MODEL_PATH']).replace('${draft}', paths['DRAFT_PATH'])
                                   .replace('${dspine}', paths.get('DSPINE_PATH', '')) for a in args], low=4)
    name = environ.get('SERVED_MODEL_NAME', 'qwen3.8-27b-atlas')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', name):
        raise ValueError('Invalid SERVED_MODEL_NAME')
    args += ['--bind=127.0.0.1', '--port=8893', f'--model-name={name}']
    args += tool_guard_args(environ, args)
    return ['/usr/local/bin/spark', *args], env


def launch(environ, profile):
    if profile.get('model') == SINGLE_MODEL:
        return launch_single(environ, profile)
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
    # NCCL advertises the first IPv4 of its socket interface. A node whose link
    # netdev also carries an address the peer reaches only off the link names
    # another bootstrap interface, and pins the RoCE GID on its rails.
    socket_interface = environ.get('FABRIC_SOCKET_INTERFACE') or interface
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', socket_interface):
        raise ValueError('Invalid fabric socket interface')
    gid = environ.get('FABRIC_GID_INDEX', '')
    if gid and not (re.fullmatch(r'0|[1-9][0-9]{0,2}', gid) and int(gid) <= 255):
        raise ValueError('FABRIC_GID_INDEX must be 0 to 255')
    siblings = environ.get('FABRIC_SIBLINGS', '0')
    if siblings not in ('0', '1'):
        raise ValueError('FABRIC_SIBLINGS must be 0 or 1')
    hcas = fabric_hcas(environ.get('FABRIC_HCA', ''), siblings=siblings == '1')
    model = environ.get('MODEL_PATH', '/models/checkpoint')
    if not Path(model).is_absolute() or any(c in model for c in '\r\n\0'):
        raise ValueError('MODEL_PATH must be an absolute path')
    # Profile values intentionally win over ambient optimization flags. Runtime
    # changes require a new reviewed image/profile instead of accidental tuning.
    env = _engine_env(environ, profile)
    env.update(precision)
    env['SPARKQWEN_MODE'] = mode
    env.update(disk_prefix_cache(environ.get('SPARKQWEN_PREFIX_CACHE_GB', ''), mode))
    env['NCCL_SOCKET_IFNAME'] = env['GLOO_SOCKET_IFNAME'] = socket_interface
    env['NCCL_IB_HCA'] = ','.join(hcas)
    # The engine's direct RDMA all-reduce stripes over the same devices.
    env['ATLAS_RDMA_RAILS'] = env['NCCL_IB_HCA']
    if gid:
        # NCCL's IB transport and the engine's RDMA pair use the same GID.
        env['NCCL_IB_GID_INDEX'] = env['ATLAS_RDMA_GID'] = gid
    # A dedicated pair can give the KV pool more of the unified memory than the
    # shipped default leaves free; a lower share reserves host/service memory
    # but shrinks the shared KV token pool. No context or concurrency promise.
    args = _memory_share(environ, [str(arg).replace('${model}', model) for arg in args])
    name = environ.get('SERVED_MODEL_NAME', 'qwen3.8-flash-next-atlas')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', name):
        raise ValueError('Invalid SERVED_MODEL_NAME')
    args += [f'--rank={rank}', f'--master-addr={master}', f'--master-port={port}',
             '--bind=127.0.0.1', f'--port={8893 + int(rank)}', f'--model-name={name}']
    args += tool_guard_args(environ, args)
    argv = ['/usr/local/bin/spark', *args]
    carveout = environ.get('SPARKQWEN_DISPLAY_CARVEOUT',
                           '1' if profile.get('display_carveout', False) else '0')
    if carveout not in ('0', '1'):
        raise ValueError('SPARKQWEN_DISPLAY_CARVEOUT must be 0 or 1')
    if carveout == '1':
        # Same host lock as SparkGLM: the display heap is shared by all products.
        argv = [argv[0], 'display-carveout',
                '--lock=/run/lock/sparkglm/display-carveout.lock', '--', *argv]
    return argv, env


def profile_path(environ, here):
    """The launch profile named by SPARKQWEN_PROFILE (default 8x262k)."""
    name = environ.get('SPARKQWEN_PROFILE', '8x262k')
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
    print(json.dumps({'event': 'atlas-recipe-start', **release_info(here), 'rank': env.get('NODE_RANK', '0'), 'profile': profile.stem, 'mode': env['SPARKQWEN_MODE'],
                      'opt_ins': sorted(k for k in OPT_INS if env.get(k) == '1'),
                      'source': f"{source['repository']}@{source['commit']}"}), flush=True)
    os.execve(argv[0], argv, env)


if __name__ == '__main__':
    main()
