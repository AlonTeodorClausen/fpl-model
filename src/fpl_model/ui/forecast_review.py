"""Practical post-GW review of local forecasts, without data or model refreshes."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import streamlit as st

from fpl_model.forecast_review import (
    event_readiness, read_official_context, review_forecast, reviewable_forecasts,
)
from fpl_model.label_contracts import utc
from fpl_model.io import SnapshotIntegrityError
from fpl_model.prediction_evaluation import _sha
from fpl_model.prototype_data import snapshot_paths
from fpl_model.daily_forecast_review import DAILY_REVIEW_VERSION


def metric_rows(variants,group=None):
    rows=[]
    for name,v in variants.items():
        values=v if group is None else v['by_history_group'][group]
        points=values.get('points') or {};minutes=values.get('minutes') or {};dnp=values.get('dnp') or {}
        rows.append(dict(model=name,n=values['n'],minut_bias=minutes.get('bias'),minut_MAE=minutes.get('mae'),
            minut_RMSE=minutes.get('rmse'),point_MAE=points.get('mae'),point_RMSE=points.get('rmse'),
            DNP_Brier=dnp.get('brier'),DNP_forudsagt=dnp.get('predicted'),DNP_observeret=dnp.get('observed'),CRPS=points.get('crps')))
    return rows


def preferred_review_index(choices,context,now):
    """Show the latest officially completed GW before an unfinished one."""
    def recorded_before_cutoff(choice):
        if choice.get('format')!='daily_transfer':return True
        created=choice.get('created_at')
        return bool(created and utc(choice['origin'])<=utc(created)<utc(choice['deadline_at']))
    eligible=[]
    for i,choice in enumerate(choices):
        if utc(choice['deadline_at'])>utc(now) or not recorded_before_cutoff(choice):
            continue
        if context is not None and event_readiness(context,choice['event'])['status']=='context_final_labels_still_required':
            eligible.append(i)
    if eligible:
        return max(eligible,key=lambda i:(choices[i]['event'],utc(choices[i].get('created_at') or choices[i]['origin']),
                                          utc(choices[i]['origin'])))
    past=[i for i,c in enumerate(choices) if utc(c['deadline_at'])<=utc(now) and recorded_before_cutoff(c)]
    return past[-1] if past else len(choices)-1


def outcome_source_reference(data):
    """The label capture may predate the chosen prices/deadline context."""
    history=(data.get('input_sources') or {}).get('history') or {}
    return dict(snapshot_id=history.get('snapshot_id',data.get('snapshot_id')),
                snapshot_path=history.get('snapshot_path',data.get('snapshot_path')),
                manifest_sha256=history.get('manifest_sha256',data.get('manifest_sha256')),
                as_of_at=history.get('available_at',data.get('as_of_at')))


def render_daily_review(result):
    """Display saved decisions and outcomes, never recompute a forecast."""
    from fpl_model.ui.presentation import friendly_time
    events=sorted(result['events'],key=int)
    horizon=f"GW{events[0]}" if len(events)==1 else f"GW{events[0]}–{events[-1]}"
    st.write(f"**{horizon} · Hvordan gik det gemte forslag?**")
    st.caption(f"Forslag gemt {friendly_time(result.get('report_created_at') or result['forecast_origin_at'])}. "
               'Den oprindelige prognose er ikke genberegnet.')
    team=result['team_comparison']
    if team['status']=='scored':
        left,middle,right=st.columns(3)
        left.metric('Behold holdet',f"{sum(w['hold_net_points'] for w in team['per_gw']):.1f} point")
        middle.metric('Gemt forslag',f"{sum(w['suggested_net_points'] for w in team['per_gw']):.1f} point")
        right.metric('Forslagets gevinst',f"{team['horizon_actual_gain']:+.1f} point")
    else:
        scored=sum(w['status']=='scored' for w in team['per_gw'])
        st.info(f"{scored} af {len(team['per_gw'])} runder kan opgøres for hele holdet. "
                'Samlet gevinst afventer de resterende udfald.')
    st.caption('To faste, hypotetiske planer: gemt XI, bænk, anfører, autosubs, chips og hits. '
               'Det er ikke dine faktisk gennemførte transfers. En god enkelt runde dokumenterer ikke bedre præcision.')
    team_rows=[]
    for week in sorted(team['per_gw'],key=lambda w:w['event']):
        team_rows.append(dict(GW=week['event'],Status='Opgjort' if week['status']=='scored' else 'Afventer',
            **{'Behold · point':week.get('hold_net_points'),'Forslag · point':week.get('suggested_net_points'),
               'Faktisk forskel':week.get('actual_gain'),'Forventet forskel':week.get('predicted_gain')}))
    st.dataframe(pd.DataFrame(team_rows),hide_index=True)
    if team['status']!='scored':
        st.caption('Horisonten afventer: delvise udfald er ikke summeret til en samlet realiseret gevinst.')
    st.write('**Hvor præcise var spillerprognoserne?**')
    st.caption(f"{result['all_final_count']} endelige spiller-GW-udfald · "
               f"{len(result['pending'])} afventer eller er uafklarede · "
               f"{result['variants']['model']['n']} kan sammenlignes med referencen.")
    st.caption('Modellen og tidligere pointgennemsnit måles på præcis de samme rækker. '
               'Referencen bruger kun den oprindelige historik før prognosetidspunktet. '
               'CRPS vises kun for gemte scenarier.')
    if result['variants']['model']['n']:
        st.dataframe(pd.DataFrame(metric_rows(result['variants'])),hide_index=True)
    else:
        st.info('Ingen sammenlignelig reference fra den oprindelige historik. '
                'Modeldiagnostik kan stadig vises for endelige udfald nedenfor.')
    with st.expander('Resultater pr. runde og spillergruppe'):
        for event in events:
            details=result['events'][event]
            st.write(f"**GW{event}** · {details['model_all']['n']} endelige udfald · {len(details['pending'])} afventer")
            if details['model']['n']:
                st.dataframe(pd.DataFrame(metric_rows(dict(model=details['model'],reference=details['reference']))),hide_index=True)
            if details['model_all']['n']>details['model']['n']:
                st.caption('Alle endelige modeludfald, inklusive dem uden sammenlignelig reference. '
                           'Denne tabel er ikke en sammenligning med referencen.')
                st.dataframe(pd.DataFrame(metric_rows(dict(model=details['model_all']))),hide_index=True)
        st.caption('Minut-bias = prognose − udfald. Positive tal er overvurdering. Lavere MAE, RMSE, Brier og CRPS er bedre.')
        st.caption('I dobbelte runder skaleres referencegennemsnittet med antallet af kampe; '
                   'referencens nulminutsandsynlighed antager uafhængige kampe. '
                   'Nul minutter er ikke altid fravær efter FPLs autosub-regler: kort tæller som deltagelse.')
        for group,label in [('regular','Regelmæssige spillere'),('other','Øvrige spillere'),('unresolved','Uafklaret historik')]:
            st.write(label)
            st.dataframe(pd.DataFrame(metric_rows(result['variants'],group)),hide_index=True)
        st.caption(result['variants']['model']['regular_rule'])
        for name,variant in result['variants'].items():
            position_rows=[]
            for part in variant['by_position']:
                position_rows.extend(metric_rows({name:part}))
                position_rows[-1]['position']={1:'Målmand',2:'Forsvar',3:'Midtbane',4:'Angreb'}[part['position']]
            st.dataframe(pd.DataFrame(position_rows),hide_index=True)
    with st.expander('Manglende udfald og reference'):
        for event in events:
            details=result['events'][event]
            st.write(f"GW{event} · uafklarede spillerpar",details['pending'])
            st.write(f"GW{event} · reference mangler",details['reference_missing'])
    with st.expander('Tekniske referencer'):
        st.write('Model:',result['model_version'])
        st.write('Registreret proveniens:',result['provenance_status'])
        st.caption('Lokale tidsstempler og checksums er dokumentation; de er ikke en ekstern attestering af oprettelsestiden.')
        st.write('Original scenariecache:',result['cache_status'],'Historisk reference:',result['prior_reference_status'])
        st.write('Prognosetid:',result['forecast_origin_at'])
        st.write('Verificerede inputkilder:',result['verified_input_sources'])
        st.write('Udfaldskilde:',result.get('outcome_source'))


@st.cache_data(show_spinner=False)
def _catalog(root,fingerprint):
    return reviewable_forecasts(root)


def review_matches_sources(result,forecast_sha,source,context):
    if result.get('format')=='daily_transfer' and result.get('version')!=DAILY_REVIEW_VERSION:
        return False
    recorded=(result.get('outcome_context_source') if result.get('format')=='daily_transfer'
              else (result.get('outcome_context') or {}).get('context_source'))
    return (result.get('forecast_sha256')==forecast_sha and result.get('outcome_source')==source
            and recorded==(context.get('source') if context else None))


def show_forecast_review(root,data):
    from fpl_model.ui.presentation import friendly_time
    with st.expander('Efter runden · sammenlign gemte prognoser med resultater'):
        files=list((Path(root)/'artifacts/defensive_odds').glob('*/comparison.json'))
        files+=list((Path(root)/'artifacts/model_forecasts').glob('*/forecast.json'))
        files+=list((Path(root)/'artifacts/transfers').glob('*/report.json'))
        fingerprint=tuple(sorted((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files))
        choices=_catalog(str(root),fingerprint)
        if not choices:
            st.info('Ingen gemte reelle prognoser til efterkontrol endnu.');return
        now=datetime.now(timezone.utc)
        context=None
        try:
            paths=snapshot_paths(Path(root)/'data/raw')
            if paths:context=read_official_context(paths[0])
        except (ValueError,OSError,KeyError,SnapshotIntegrityError) as exc:
            st.error(f'Kampkontekst kunne ikke verificeres: {exc}')
        index=preferred_review_index(choices,context,now)
        chosen=st.selectbox('Prognose til efterkontrol',choices,index=index,
            format_func=lambda c:f"GW{c['event']} · {friendly_time(c.get('created_at') or c['origin'])} · " +
                ('dagligt transferforslag' if c['format']=='daily_transfer' else
                 'gemte simulationer' if c['format']=='saved_scenarios' else 'gemte nøgletal'),
            key='review_forecast_choice')
        st.caption(f"Prognose: {friendly_time(chosen['origin'])} · officiel deadline: {friendly_time(chosen['deadline_at'])}. Tiderne er dansk tid.")
        st.caption('Standardvalget er sidste gemte kørsel før deadline for den seneste afsluttede runde. Valget bruger ikke udfald eller performance.')
        if context:
            readiness=event_readiness(context,chosen['event'])
            st.write(f"**Officiel rundestatus:** {readiness['finished']}/{readiness['fixtures']} kampe endelige · "
                     f"{readiness['provisionally_finished']} foreløbigt afsluttede · GW datakontrolleret: {'ja' if readiness['event_data_checked'] else 'nej'}")
            st.caption(f"Rundestatus hentet {friendly_time(context['source']['available_at'])}")
            if readiness['status']=='awaiting_official_finality':
                st.warning('Afventer officielle slutresultater. Afsluttede kampe og forløbet kamptid er ikke tilstrækkelige til endelige labels.')
            else:st.info('Kampkonteksten er endelig. Spillerhistorikker skal også være hentet med endelige labels før evaluering.')
            unfinished=[f for f in readiness['remaining'] if not f['finished_provisional']]
            if unfinished:st.dataframe(pd.DataFrame(unfinished),hide_index=True)
        else:st.warning('Ingen verificeret lokal kampkontekst til rundestatus.')
        source=outcome_source_reference(data)
        st.caption(f"Spillerudfald hentet {friendly_time(source['as_of_at']) if source['as_of_at'] else 'på ukendt tidspunkt'}. En nyere kampkontekst opgraderer ikke ældre spillerlabels.")
        if chosen['format']=='legacy_summary':
            st.caption('Ældre prognose: middelværdier, DNP og percentiler er gemt; fulde scenarier mangler. Derfor vises CRPS som manglende. Oprindelig oprettelsestid er deklareret, ikke uafhængigt bevist.')
        elif chosen['format']=='daily_transfer':
            st.caption('Dagligt transferforslag: evalueringen bruger kun den gemte rapport og dens oprindelige cache, hvis den findes. Ingen senere data bliver forecast-input.')
        if st.button('Efterkontrollér gemt prognose'):
            try:
                out,_=review_forecast(chosen['path'],data['histories'],Path(root)/'artifacts/forecast_reviews',
                    season=data.get('season','2026-2027'),context=context,outcome_source=source)
                st.success('Efterkontrollen er gemt. Den oprindelige prognose er uændret.')
            except (ValueError,OSError,KeyError,SnapshotIntegrityError) as exc:st.error(f'Efterkontrol afvist: {exc}')
        # Read local persisted results; do not silently reuse scores against different outcomes.
        checks=sorted((Path(root)/'artifacts/forecast_reviews').glob('*/report.json'),reverse=True)
        result=None;forecast_sha=_sha(chosen['path'])
        for p in checks:
            try:r=json.loads(p.read_bytes())
            except (ValueError,OSError):continue
            if review_matches_sources(r,forecast_sha,source,context):
                result=r;break
        if result is None:
            st.info('Ingen efterkontrol gemt for denne prognose og det valgte udfaldssnapshot.');return
        if result.get('format')=='daily_transfer':
            render_daily_review(result)
            return
        total=len(next(iter(result['variants'].values()))['pending'])+len(result['same_player_ids'])
        st.info(f"{len(result['same_player_ids'])} spillere med komplette endelige udfald af {total}. Samme evalueringsrækker for alle varianter.")
        st.caption(f"Efterkontrol gemt {result['created_at']} · proveniens: {result['provenance_status']}. Manglende/provisoriske rækker er aldrig DNP.")
        st.dataframe(pd.DataFrame(metric_rows(result['variants'])),hide_index=True)
        st.caption('Bias = prognose − observeret. Negative minutter betyder undervurdering. CRPS kræver gemte scenarier. En enkelt eller ufuldstændig runde dokumenterer ikke en bedre model.')
        st.write('**Regelmæssige spillere ud fra historikken på prognosetidspunktet**')
        st.caption(result['regular_rule']+' Ufuldstændigt historikgrundlag vises særskilt.')
        st.dataframe(pd.DataFrame(metric_rows(result['variants'],'regular')),hide_index=True)
        with st.expander('Dækning, positioner og spillerfejl'):
            for name,v in result['variants'].items():
                st.write(name,'Afventer:',v['pending_reasons'])
                st.dataframe(pd.DataFrame(v['by_position']),hide_index=True)
                st.write('Andre spillere og uafklaret historik:',{k:v['by_history_group'][k] for k in ('other','unresolved')})
                if v['rows']:st.dataframe(pd.DataFrame(v['rows']),hide_index=True)
                if v['pending']:st.dataframe(pd.DataFrame(v['pending']),hide_index=True)
