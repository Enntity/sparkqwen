# SPDX-License-Identifier: AGPL-3.0-only
import json, subprocess, sys
from pathlib import Path
ENGINE = 'f1fdf272cd54322ce82ad40814e19ef9915949f3'
TREE = 'f3b0524eb5925a9978d803718e721440ba323b2c'
INSTALL = 'e3bb830b0c662b1a547a8c8d5aba1a37fed3c25b'
kind = sys.argv[1]
image = ('atlas-qwen-common-campaign:' + ENGINE[:12] if kind == 'campaign'
         else 'ghcr.io/enntity/atlas-sparkqwen:' + INSTALL[:12])
def run(*args):
    return subprocess.check_output(args, text=True).strip()
info = json.loads(run('docker', 'image', 'inspect', image))[0]
if kind == 'campaign':
    identity = run('docker','run','--rm','--entrypoint','git',image,
                   '-C','/build','rev-parse','HEAD','HEAD^{tree}').splitlines()
    assert identity == [ENGINE, TREE], identity
else:
    source = json.loads(run('docker','run','--rm','--entrypoint','cat',image,
                            '/opt/atlas/source-manifest.json'))
    assert (source['commit'], source['tree']) == (ENGINE, TREE)
    pin = json.loads(Path('candidate-product18/install/atlas-source.json').read_text())
    assert (pin['commit'], pin['tree']) == (ENGINE, TREE)
    version = run('docker','run','--rm',image,'--version')
    assert version.splitlines() == ['SparkQwen 0.2.0', 'Atlas '+ENGINE, 'Engine tree '+TREE], version
    assert info['Config']['Labels']['org.opencontainers.image.version'] == '0.2.0'
    assert info['Config']['Labels']['io.enntity.sparkqwen.install-tree'] == INSTALL
binary = run('docker','run','--rm','--entrypoint','sha256sum',image,'/usr/local/bin/spark').split()[0]
print(json.dumps({'kind': kind, 'image': image, 'image_id': info['Id'],
                  'engine_commit': ENGINE, 'engine_tree': TREE,
                  'binary_sha256': binary, 'validated': True}, indent=2))
