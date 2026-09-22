"""Transfer research with credentials supplied by ``local_credentials run``.

python -m scripts.research_transfer export --root PATH --output archive.json
python -m bktstr.local_credentials run -- python -m scripts.research_transfer upload --input archive.json
python -m bktstr.local_credentials run -- python -m scripts.research_transfer preserve --input older-archive.json
python -m bktstr.local_credentials run -- python -m scripts.research_transfer download --output server.json
python -m scripts.research_transfer import --root RESTORE_PATH --input server.json
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from bktstr.dataset_snapshots import atomic_text
from bktstr.research_ideas import canonical
from bktstr.services.experiments import ExperimentStore
from bktstr.services.research_transfer import MAX_BUNDLE_BYTES, export_bundle, import_bundle, _validate


def read_bundle(path):
    path = Path(path)
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError('archive exceeds the 64 MiB transfer limit')
    bundle = json.loads(path.read_text(encoding='utf-8'))
    _validate(bundle)
    return bundle


def remote_request(method, endpoint, *, bundle=None):
    origin = os.environ.get('BKTSTR_BASE_URL', '').rstrip('/')
    key = os.environ.get('BKTSTR_API_KEY', '')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('BKTSTR_BASE_URL must be a trusted HTTPS origin without a path')
    if not key:
        raise ValueError('run through the local credential helper; no API key was supplied')
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        with client.stream(method, origin + endpoint,
                           headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                           content=canonical(bundle).encode('utf-8') if bundle is not None else None) as response:
            if response.status_code != 200:
                raise ValueError(f'server rejected archive operation (HTTP {response.status_code})')
            chunks, count = [], 0
            for chunk in response.iter_bytes():
                count += len(chunk)
                if count > MAX_BUNDLE_BYTES:
                    raise ValueError('server archive exceeds the 64 MiB transfer limit')
                chunks.append(chunk)
            return json.loads(b''.join(chunks))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('export', 'import', 'upload', 'preserve', 'download'):
        command = commands.add_parser(name)
        if name in {'export', 'import'}:
            command.add_argument('--root', type=Path, required=True)
        command.add_argument('--output' if name in {'export', 'download'} else '--input', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'export':
            if not (args.root / 'experiments.sqlite3').is_file():
                raise ValueError('source experiment database does not exist')
            bundle = export_bundle(ExperimentStore(args.root))
        elif args.command == 'download':
            bundle = remote_request('GET', '/api/v1/research/archive/export')
            _validate(bundle)
        else:
            bundle = read_bundle(args.input)
            result = import_bundle(ExperimentStore(args.root), bundle) if args.command == 'import' else remote_request(
                'POST', '/api/v1/research/archives' if args.command == 'preserve' else '/api/v1/research/archive/import', bundle=bundle)
            print(canonical(result))
            return 0
        if args.output.exists():
            raise ValueError('output exists; choose a new archive filename')
        atomic_text(args.output, canonical(bundle))
        print(canonical(dict(path=str(args.output.resolve()), digest=bundle['digest'],
                             experiments=len(bundle['tables']['experiments']))))
        return 0
    except ValueError as exc:
        print(f'Archive operation failed: {exc}')
        return 1
    except (OSError, httpx.HTTPError):
        # Never echo arbitrary response bodies, request objects, or headers.
        print('Archive operation failed. Check archive integrity, identity conflicts, server availability, and credentials.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
