#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Ask SparkQwen about a local clip using the standard library only."""
import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clip', type=Path)
    parser.add_argument('--prompt', default=(
        'Describe the visible sequence of events. Give approximate timestamps '
        'in seconds for each event. Separate observations from uncertainty.'
    ))
    parser.add_argument('--base-url', default='http://127.0.0.1:8893/v1')
    parser.add_argument('--max-tokens', type=int, default=1024)
    args = parser.parse_args()
    mime = mimetypes.guess_type(args.clip.name)[0] or 'video/mp4'
    uri = 'data:' + mime + ';base64,' + base64.b64encode(args.clip.read_bytes()).decode()
    payload = {
        'model': 'qwen3.8-flash-next-atlas',
        'messages': [{'role': 'user', 'content': [
            {'type': 'video_url', 'video_url': {'url': uri}},
            {'type': 'text', 'text': args.prompt},
        ]}],
        'max_tokens': args.max_tokens,
        'temperature': 0,
        'reasoning_effort': 'low',
    }
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('OPENAI_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['OPENAI_API_KEY']
    request = urllib.request.Request(args.base_url.rstrip('/') + '/chat/completions',
                                     data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f'HTTP {error.code}: {error.read().decode(errors="replace")}')
    print(result['choices'][0]['message'].get('content') or '')
    print(json.dumps({'usage': result.get('usage')}, indent=2))


if __name__ == '__main__':
    main()
