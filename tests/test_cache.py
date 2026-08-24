import asyncio
from datetime import date
import pandas as pd

from bktstr.cache import BarCache, CachedProvider


def sample_bars(day: str):
    idx=pd.DatetimeIndex([f"{day} 09:30:00",f"{day} 09:31:00"],tz="America/New_York")
    return pd.DataFrame({"open":[100.,101.],"high":[101.,102.],"low":[99.,100.],"close":[100.5,101.5],"volume":[1000.,1200.]},index=idx)


class FakeProvider:
    def __init__(self): self.calls=[]
    async def fetch_bars(self,symbol,start,end,timeframe="1m"):
        self.calls.append((symbol,start,end,timeframe)); frames=[]; cursor=start
        while cursor<=end:
            if cursor.weekday()<5: frames.append(sample_bars(cursor.isoformat()))
            cursor += pd.Timedelta(days=1).to_pytimedelta()
        return pd.concat(frames).sort_index() if frames else pd.DataFrame(columns=["open","high","low","close","volume"])


def test_bar_cache_round_trip(tmp_path):
    c=BarCache(tmp_path); d=date(2026,8,17); b=sample_bars(d.isoformat()); c.write_day("massive","NVDA","1m",d,b)
    restored=c.read_day("massive","NVDA","1m",d)
    assert restored is not None and restored.equals(b) and restored.index.tz is not None


def test_bar_cache_records_empty_days(tmp_path):
    c=BarCache(tmp_path); d=date(2026,8,22); empty=pd.DataFrame(columns=["open","high","low","close","volume"])
    c.write_day("massive","NVDA","1m",d,empty); restored=c.read_day("massive","NVDA","1m",d)
    assert restored is not None and restored.empty


def test_cached_provider_fetches_once_then_hits(tmp_path):
    upstream=FakeProvider(); p=CachedProvider(upstream,BarCache(tmp_path),provider_name="massive",today_fn=lambda:date(2026,8,20))
    start=date(2026,8,17); end=date(2026,8,18)
    first=asyncio.run(p.fetch_bars("NVDA",start,end,"1m")); first_stats=p.last_stats
    second=asyncio.run(p.fetch_bars("NVDA",start,end,"1m")); second_stats=p.last_stats
    assert len(upstream.calls)==1 and second.equals(first)
    assert first_stats=={"hit_days":0,"miss_days":2,"fetched_ranges":1}
    assert second_stats=={"hit_days":2,"miss_days":0,"fetched_ranges":0}


def test_current_day_is_never_reused(tmp_path):
    upstream=FakeProvider(); p=CachedProvider(upstream,BarCache(tmp_path),provider_name="massive",today_fn=lambda:date(2026,8,17))
    asyncio.run(p.fetch_bars("NVDA",date(2026,8,17),date(2026,8,17),"1m")); asyncio.run(p.fetch_bars("NVDA",date(2026,8,17),date(2026,8,17),"1m"))
    assert len(upstream.calls)==2
