"""Research catalog in the existing experiment database, with immutable artifacts."""
from contextlib import closing, contextmanager
import json
import re
from uuid import uuid4
from datetime import datetime, timezone

from ..dataset_snapshots import atomic_text
from ..research_ideas import canonical, digest, parse_revision, Ref


class ResearchCatalog:
    def __init__(self, store):
        self.store = store
        self.root = store.root / 'research'
        self.datasets = self.root / 'datasets'
        self.artifacts = self.root / 'artifacts'
        self.reports = self.root / 'reports'
        for path in (self.datasets, self.artifacts, self.reports):
            path.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS research_revisions (kind TEXT NOT NULL, id TEXT NOT NULL, version TEXT NOT NULL, digest TEXT NOT NULL, document TEXT NOT NULL, PRIMARY KEY(kind,id,version))')
            db.execute('CREATE TABLE IF NOT EXISTS research_assessments (id TEXT PRIMARY KEY, idea_id TEXT NOT NULL, created_at TEXT NOT NULL, document TEXT NOT NULL)')

    @contextmanager
    def transaction(self):
        with closing(self.store._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def register(self, kind, document):
        revision = parse_revision(kind, document)
        with self.transaction() as db:
            previous = db.execute('SELECT digest FROM research_revisions WHERE kind=? AND id=? AND version=?',
                                  (kind, revision.id, revision.version)).fetchone()
            if previous and previous['digest'] != revision.digest:
                raise ValueError('immutable revision identity already has different content')
            db.execute('INSERT OR IGNORE INTO research_revisions VALUES (?,?,?,?,?)',
                       (kind, revision.id, revision.version, revision.digest, revision.canonical_json))
        return revision

    def require(self, ref, kind=None):
        ref = Ref.model_validate(dict(ref)).model_dump()
        with closing(self.store._connect()) as db:
            rows = db.execute('SELECT * FROM research_revisions WHERE id=? AND version=? AND digest=?',
                              (ref['id'], ref['version'], ref['digest'])).fetchall()
        rows = [r for r in rows if kind is None or r['kind'] == kind]
        if len(rows) != 1:
            raise ValueError('missing or ambiguous pinned revision')
        result = parse_revision(rows[0]['kind'], json.loads(rows[0]['document']))
        if result.digest != ref['digest']:
            raise ValueError('revision digest mismatch')
        return result

    def revisions(self, kind=None):
        with closing(self.store._connect()) as db:
            rows = db.execute('SELECT * FROM research_revisions ORDER BY kind,id,version').fetchall()
        return [self.require(dict(id=r['id'], version=r['version'], digest=r['digest']), r['kind'])
                for r in rows if kind is None or r['kind'] == kind]

    def save_artifact(self, document):
        artifact_id = digest(document)
        destination = self.artifacts / f'{artifact_id}.json'
        text = canonical(document)
        if destination.exists() and destination.read_text(encoding='utf-8') != text:
            raise ValueError('immutable artifact corruption')
        atomic_text(destination, text)
        return artifact_id

    def load_artifact(self, artifact_id):
        if not re.fullmatch('[0-9a-f]{64}', artifact_id):
            raise ValueError('invalid artifact digest')
        value = json.loads((self.artifacts / f'{artifact_id}.json').read_text(encoding='utf-8'))
        if digest(value) != artifact_id:
            raise ValueError('artifact digest mismatch')
        return value

    def assess(self, idea_id, *, author, conclusion, evidence, limitations):
        if not all(isinstance(x, str) and x.strip() for x in (author, conclusion, limitations)):
            raise ValueError('assessment requires author, conclusion, limitations')
        if not any(x.id == idea_id for x in self.revisions('idea')):
            raise ValueError('unknown idea')
        for experiment_id in evidence:
            record = self.store.load_experiment(experiment_id)
            if record.request.get('idea', {}).get('id') != idea_id:
                raise ValueError('assessment evidence belongs to another idea')
        document = dict(author=author, conclusion=conclusion, evidence=list(evidence), limitations=limitations)
        assessment_id = 'assessment_' + uuid4().hex
        with self.transaction() as db:
            db.execute('INSERT INTO research_assessments VALUES (?,?,?,?)',
                (assessment_id, idea_id, datetime.now(timezone.utc).isoformat(), canonical(document)))
        return assessment_id

    def assessments(self, idea_id):
        with closing(self.store._connect()) as db:
            rows = db.execute('SELECT * FROM research_assessments WHERE idea_id=? ORDER BY created_at,id', (idea_id,)).fetchall()
        return [dict(id=r['id'], created_at=r['created_at'], **json.loads(r['document'])) for r in rows]
