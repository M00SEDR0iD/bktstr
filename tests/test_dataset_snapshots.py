import asyncio
import pandas as pd
import pytest


def sample_frames(missing=False):
    index = pd.date_range('2026-08-17 13:30', periods=6, freq='min', tz='UTC')
    close = [100, 99, 102, 98, 103, 104]
    frame = pd.DataFrame(dict(open=close, high=[x+1 for x in close], low=[x-1 for x in close], close=close, volume=100), index=index)
    return {'SPY': frame.drop(index[2]) if missing else frame}


def sample_schedule():
    return [dict(date='2026-08-17', open='2026-08-17T13:30:00+00:00', close='2026-08-17T13:36:00+00:00')]


def test_snapshot_is_immutable_and_corruption_blocks_replay(tmp_path):
    from bktstr.dataset_snapshots import freeze_dataset, load_snapshot, SnapshotProvider
    frames = sample_frames()
    snap = freeze_dataset(frames, sample_schedule(), tmp_path, source='synthetic')
    frames['SPY'].iloc[0, 0] = 1
    replay = load_snapshot(snap.id, tmp_path)
    assert replay.frame('SPY').iloc[0]['open'] == 100
    provider = SnapshotProvider(replay)
    from datetime import date
    assert len(asyncio.run(provider.fetch_bars('SPY', date(2026,8,17), date(2026,8,17), '1m'))) == 6
    with pytest.raises(ValueError):
        asyncio.run(provider.fetch_bars('QQQ', date(2026,8,17), date(2026,8,17), '1m'))
    (tmp_path / f'{snap.id}.json').write_text('{}')
    with pytest.raises(ValueError, match='digest'):
        load_snapshot(snap.id, tmp_path)


def test_coverage_and_input_quality(tmp_path):
    from bktstr.dataset_snapshots import freeze_dataset
    with pytest.raises(ValueError, match='coverage'):
        freeze_dataset(sample_frames(True), sample_schedule(), tmp_path, source='synthetic')
    snap = freeze_dataset(sample_frames(True), sample_schedule(), tmp_path, source='synthetic', controlled=False)
    assert snap.document['coverage']['SPY']['missing'] == 1
    frames = sample_frames()
    frames['SPY'] = pd.concat([frames['SPY'], frames['SPY'].iloc[:1]])
    with pytest.raises(ValueError, match='duplicate|sorted'):
        freeze_dataset(frames, sample_schedule(), tmp_path, source='synthetic')


def test_snapshot_cannot_escape_root(tmp_path):
    from bktstr.dataset_snapshots import load_snapshot
    with pytest.raises(ValueError):
        load_snapshot('../outside', tmp_path)
