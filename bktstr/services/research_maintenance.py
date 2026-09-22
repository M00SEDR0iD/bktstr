"""Idle-time daily online backups and conservative dataset expiry."""
from datetime import datetime, timedelta, timezone
import gzip
import json
import os
from pathlib import Path
from uuid import uuid4

from .research_store import ResearchCatalog
from .research_storage import cleanup


def maintain(store, *, force=False):
    from .research_transfer import export_bundle
    catalog = ResearchCatalog(store)
    now = datetime.now(timezone.utc)
    root = catalog.root / 'backups'
    if root.is_symlink() or not root.resolve().is_relative_to(store.root.resolve()):
        raise ValueError('unsafe backup directory')
    root.mkdir(exist_ok=True)
    name = now.date().isoformat() + '.json.gz'
    path = root / name
    if path.is_symlink():
        raise ValueError('unsafe backup path')
    if force or not path.exists():
        bundle = export_bundle(store, max_bytes=None)
        temporary = root / (uuid4().hex + '.tmp')
        try:
            with gzip.open(temporary, 'wt', encoding='utf-8') as stream:
                json.dump(bundle, stream, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    # A backup must succeed before any automatic input eviction.
    result = cleanup(catalog, apply=True)
    for old in root.glob('????-??-??.json.gz'):
        if old.is_symlink():
            raise ValueError('unsafe backup path')
        if old.name[:10] < (now - timedelta(days=7)).date().isoformat():
            old.unlink()
    return dict(backup=name, cleanup=result)


def status(store):
    root = ResearchCatalog(store).root / 'backups'
    backups = sorted(p.name for p in root.glob('????-??-??.json.gz') if p.is_file() and not p.is_symlink())
    mount = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
    return dict(persistent_volume=bool(mount and store.root.resolve().is_relative_to(Path(mount).resolve())),
                backups=backups, latest_backup=backups[-1] if backups else None)
