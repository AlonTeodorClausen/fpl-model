"""One fresh official context plus the player pool it actually names. No freeze."""
import json
import math
import re
import time
from contextlib import nullcontext

import requests

from fpl_model.data_sources.fpl_api import fetch_fpl_snapshot, _utc_now
from fpl_model.data_sources.fpl_player_history import fetch_player_histories, validate_element_ids
from fpl_model.io import SnapshotWriter


def capture_all_players(raw_root, *, season, session=None, clock=_utc_now,
                        sleep=time.sleep, request_interval=.5, progress=None):
    if not re.fullmatch(r'\d{4}-\d{4}',season) or int(season[5:])!=int(season[:4])+1:
        raise ValueError('Explicit YYYY-YYYY season required')
    if not math.isfinite(request_interval) or request_interval<.25:
        raise ValueError('At least 0.25 seconds between requests required')
    writer=SnapshotWriter(raw_root,clock=clock)
    metadata=dict(purpose='official_full_player_history',season=season,history_scope='bootstrap_all',
                  request_interval=str(request_interval),max_attempts='3')
    writer.set_run_metadata(metadata)
    try:
        with requests.Session() if session is None else nullcontext(session) as client:
            fetch_fpl_snapshot(writer,session=client,clock=clock)
            bootstrap=json.loads((writer.staging_path/'raw/fpl_api/bootstrap_static.json').read_bytes())
            ids=validate_element_ids(p['id'] for p in bootstrap['elements'])
            metadata['player_count']=str(len(ids));writer.set_run_metadata(metadata)
            sleep(request_interval)
            results=fetch_player_histories(writer,ids,session=client,clock=clock,sleep=sleep,
                required=False,max_attempts=3,request_interval=request_interval,progress=progress)
        success=sum(r['status']=='success' for r in results)
        writer.set_run_metadata({**metadata,'successful_players':str(success),
            'attempted_players':str(sum(r['attempts']>0 for r in results)),
            'overall':'complete' if success==len(ids) else 'partial'})
        return writer.finalize()
    except BaseException:
        writer.mark_failed()
        raise
