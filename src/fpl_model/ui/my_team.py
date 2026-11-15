"""Personal-team editor and transfer comparisons. Team import is an explicit action."""
from datetime import datetime, timezone
from collections import Counter
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from fpl_model.config import ROOT
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import BaselineConfig
from fpl_model.my_team import money, validate_profile, save_profile, load_profile, reconcile_sale_prices
from fpl_model import prototype_data
from fpl_model import quick_refresh
from fpl_model.public_data import read_active_public_data
from fpl_model.readiness import assess_deadline_readiness
from fpl_model.data_sources.fpl_api import FPLSourceError
from fpl_model.io import SnapshotError
from fpl_model.odds_comparison import load_odds
from fpl_model.transfer_planner import forecast_bundle, compare_packages, save_report
from fpl_model.sequence_planner import compare_sequences, compare_sensitivity
from fpl_model.ui.strategy import (availability_controls, scenario_records,
                                   show_sequence_report, show_decision_evidence)
from fpl_model.ui.team_import import render_import
from fpl_model.ui.guest_state import guest_mode, guest_root, parse_guest_profile_bytes
from fpl_model.ui.guest_limits import GuestLimitError,claim_guest_job
from fpl_model.ui.player_detail import (selected_owned_id, comparison_rows, point_distribution,
                                        bundle_for_report)
from fpl_model.ui.decision_summary import immediate_decision, sequence_decision, alternative_previews
from fpl_model.ui.presentation import (friendly_time, team_html, saved_comparison_option,
                                        show_lineup, snapshot_option, transfer_card, summary_metrics,
                                        decision_overview_html, readiness_message, next_step_card_html,
                                        official_media, quarantine_reason_label)

LOCAL_ROOT = ROOT
POSITIONS = {1: ('Målmand',2), 2: ('Forsvarer',5), 3: ('Midtbane',5), 4: ('Angriber',3)}
EXAMPLE_NAMES = ['Verbruggen','Steele','Konsa','De Cuyper','Gvardiol','Ajer','Egan',
                 'Cherki','Rogers','Szoboszlai','B.Fernandes','Slater','Wissa','Haaland','João Pedro']


@st.cache_data(show_spinner=False, max_entries=16)
def _load_data(path, manifest_stamp, history_path, history_stamp, season):
    if Path(path).resolve()==Path(history_path).resolve():
        return prototype_data.load_data(Path(path),season=season,include_season_history=True)
    return quick_refresh.load_current_inputs(Path(path),Path(history_path),season=season,
                                             include_season_history=True, allow_incomplete_history=True)


def _manifest_stamp(path):
    manifest=Path(path)/'manifest.json'
    return manifest.stat().st_mtime_ns if manifest.exists() else 0


@st.cache_data(show_spinner=False, max_entries=64)
def _select_history(paths, manifest_stamps, chosen, season):
    # Cache the audited anchor search against the complete local inventory. A new
    # capture invalidates it; ordinary reruns never normalize all old captures.
    return quick_refresh.select_history_snapshot([Path(p) for p in paths],Path(chosen),season=season,
                                                 include_incomplete=True)


def _load_local_choice(paths, chosen, season, *, allow_history_fallback):
    remaining=list(paths)
    skipped=[]
    while remaining:
        history=_select_history(tuple(str(p) for p in remaining),
            tuple(_manifest_stamp(p) for p in remaining),str(chosen),season)
        if history is None:
            raise ValueError('Ingen tidligere komplet spillerhistorik før dette snapshot. '
                             'Hent fuld spillerhistorik først.')
        try:
            data=_load_data(str(chosen),_manifest_stamp(chosen),
                            str(history),_manifest_stamp(history),season)
        except (SnapshotError,OSError,ValueError,KeyError,TypeError) as exc:
            if not allow_history_fallback or history==chosen or history not in remaining:
                raise
            # Try each earlier full-pool anchor once. Compatibility and label
            # completeness still go through the existing audited loader.
            skipped.append((history,str(exc)))
            remaining.remove(history)
        else:
            return history,data,skipped
    raise ValueError('Ingen kompatibel komplet spillerhistorik til denne kontekst.')


def _capture_time(path):
    try:
        manifest=json.loads((Path(path)/'manifest.json').read_text())
        times=[utc(e.get('available_at',e.get('retrieved_at'))) for e in manifest['files']
               if e.get('source')=='fpl_api' and e.get('outcome')=='success'
               and e.get('relative_path','').endswith(('/bootstrap_static.json','/fixtures.json'))
               and (e.get('available_at') or e.get('retrieved_at'))]
        return friendly_time(max(times)) if times else 'ukendt hentetid'
    except (OSError,ValueError,KeyError,TypeError):
        return 'ukendt hentetid'


def _reset_editor(profile):
    for key in list(st.session_state):
        if key.startswith('owned_'):
            del st.session_state[key]
    st.session_state.pop('sale_adjusted_ids',None)
    st.session_state['team_draft'] = profile


def _clear_sale(slot):
    st.session_state[f'owned_sale_{slot}'] = None


def _example(players, season):
    selected = []
    for name in EXAMPLE_NAMES:
        matches = [p for p in players if p['web_name']==name]
        if len(matches)!=1:
            raise ValueError(f'Eksempelspiller {name} kan ikke matches entydigt i dette snapshot.')
        selected.append(dict(player_id=matches[0]['id'],selling_price=None))
    return dict(schema_version=1,season=season,players=selected,bank=None,free_transfers=1,transfers_made=0)


def _odds_paths(root):
    paths = []
    for path in sorted((root/'data/raw').glob('*/manifest.json'), reverse=True):
        if not (path.parent/'COMPLETE').is_file():
            continue
        try:
            manifest = json.loads(path.read_text())
            if any(f['source']=='the_odds_api' for f in manifest['files']):
                paths.append(path.parent)
        except (OSError, ValueError, KeyError):
            continue
    return paths


def show_report(report, *, compact=False, media_by_id=None):
    input_readiness=report.get('input_readiness') or {}
    if input_readiness.get('new_forecast_status')=='limited':
        st.warning('Denne gemte prognose blev beregnet med ufuldstændige data efter udtrykkeligt valg. '
                   'Åbn Berørte input i denne beregning; brug den som en foreløbig vurdering.')
        first=next(iter(report.get('players_by_event',{}).values()),[])
        names={row['player_id']:row['name'] for row in first}
        sources=report.get('forecast',{}).get('input_sources') or {}
        with st.expander('Berørte input i denne beregning'):
            st.write('Begrænsninger:',readiness_message(input_readiness.get('limited_reasons',[])))
            st.write('Spillere uden svar:',[names.get(i,str(i)) for i in input_readiness.get('missing_player_ids',[])])
            st.write('Spillere med karantænerækker:',
                     [names.get(i,str(i)) for i in input_readiness.get('quarantined_player_ids',[])])
            st.write('Ændrede kampe:',input_readiness.get('changed_fixture_ids',[]))
            st.write('Igangværende kampe:',input_readiness.get('in_progress_fixture_ids',[]))
            st.write('Karantænerækker:',input_readiness.get('quarantined_rows',0))
            for reason,count in input_readiness.get('quarantine_reason_counts',{}).items():
                st.caption(f'{quarantine_reason_label(reason)}: {count}')
            for label,key in (('Priser og status','official_context'),('Spillerhistorik','history')):
                observed=(sources.get(key) or {}).get('available_at')
                if observed:st.caption(f'{label} hentet {friendly_time(observed)}')
    if report.get('scope')=='transfer_sequences':
        return show_sequence_report(report,compact=compact,media_by_id=media_by_id)
    forecast = report['forecast']
    st.subheader('Ugeplan og opstillinger' if compact else 'Transferforslag')
    estimated_sales=report.get('profile',{}).get('price_estimate_ids',[])
    if estimated_sales:
        count=len(estimated_sales)
        st.warning(f'{count} salgsværdi' + (' var' if count==1 else 'er var') + ' estimeret ud fra listepriser. '
                   'Budget og bank efter transfers er derfor foreløbige; kontrollér udgående spilleres reelle salgsværdier i FPL.')
    st.caption(f"Beregnet {friendly_time(forecast['forecast_origin_at'])} · alle transfers sker nu")
    first = next(iter(report['players_by_event'].values()))
    pool = {r['player_id']: r for r in first}
    names = lambda ids: ', '.join(pool[i]['name'] for i in ids) or '—'
    decision = immediate_decision(report)
    if not compact:
        st.write('**Forslag til næste deadline**')
        st.success('Behold truppen denne uge.' if decision['count']==0 else
                   f"{decision['count']} transfer(s): {names(decision['out'])} ud · {names(decision['in'])} ind.")
        summary_metrics([
            ('Næste GW',f"{decision['next_gw_gain']:+.2f}",'Simuleret gevinst mod behold'),
            ('Hele horisonten',f"{decision['horizon_gain']:+.2f}",'Simuleret gevinst mod behold'),
            ('Bank efter',f"£{decision['bank_after']/10:.1f}m",f"{decision['hits']} pointfradrag")])
        st.caption('Gevinster er simulerede. Små forskelle kan være støj.')
    rows = []
    for p in report['packages']:
        rows.append(dict(Forslag='Behold holdet' if p['count']==0 else f"{p['count']} transfers",
            Ud=names(p['out']), Ind=names(p['in']), **{'Bank £m':p['bank_after']/10,
            'Gratis brugt':p['transfer_schedule'][0]['used'],'Hits':p['hits'],
            'Gevinst næste GW':round(p['next_gw_gain'],3),'Gevinst horisont':round(p['total_gain'],3),
            'Simulerede point, netto':round(p['total_points'],3),'Målværdi, netto':round(p['objective'],3),
            'FT næste GW':p['transfer_schedule'][0]['next_gw'],'Solver':p['solver']['status'],
            'Gap %':100*p['solver']['gap']}))
    with st.expander('Sammenlign alle forslag · point, transfers og solver'):
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    for failure in report['unavailable_packages']:
        st.warning(failure['reason'])
    cfg = report['config']
    if cfg['max_transfers'] != cfg['effective_max_transfers']:
        st.caption(f"Grænserne tillader højst {cfg['effective_max_transfers']} nye transfers i denne kørsel.")
    options = list(range(len(report['packages'])))
    report_id=(report.get('created_at'),forecast.get('cache_key'),
               tuple((p['count'],p['objective']) for p in report['packages']))
    if st.session_state.get('proposal_detail_report')!=report_id:
        st.session_state['proposal_detail_report']=report_id
        st.session_state['proposal_detail']=max(options,key=lambda i:(
            report['packages'][i]['objective'],-report['packages'][i]['count']))
    index = st.selectbox('Forslag – se opstillinger', options,
                        format_func=lambda i: rows[i]['Forslag'],key='proposal_detail')
    proposal = report['packages'][index]
    transfer_card(rows[index]['Forslag'],names(proposal['out']),names(proposal['in']),proposal['bank_after'],proposal['hits'],proposal['total_gain'])
    show_decision_evidence(report,proposal)
    st.write('Gratis transfers gennem horisonten (ingen yderligere køb):')
    st.dataframe(pd.DataFrame(proposal['transfer_schedule']).rename(columns={
        'event':'GW','available':'Til rådighed','used':'Gratis brugt','remaining':'Tilbage',
        'next_gw':'Til næste GW','hits':'Pointfradrag'}),hide_index=True)
    st.caption('Opsparing vises som regnskab. Værdien af at vente er ikke fuldt optimeret.')
    st.dataframe(pd.DataFrame([{k:v for k,v in week.items() if k!='player_mean_points'}
                               for week in proposal['per_gw']]).rename(columns={
        'event':'GW','mean':'Simulerede point, netto','gain':'Gevinst mod behold','objective':'Målværdi, netto',
        'bench_mean':'Autosub-point','hits':'Pointfradrag'}),hide_index=True)
    lineup_view=st.radio('Opstillingsvisning',['Liste','Bane'],horizontal=True,key='package_lineup_view')
    tabs=st.tabs([f'GW{e}' for e in proposal['lineups']])
    for tab,(event, lineup) in zip(tabs,proposal['lineups'].items()):
        table = report['players_by_event'].get(event) or report['players_by_event'].get(str(event))
        by_id = {r['player_id']:r for r in table}
        with tab, st.expander(f'GW{event} · XI, bænk og anfører', expanded=True):
            show_lineup(by_id,lineup,view=lineup_view,media_by_id=media_by_id)
            week=next(row for row in proposal['per_gw'] if int(row['event'])==int(event))
            team_contribution={int(i):v for i,v in week.get('player_mean_points',{}).items()}
            records = []
            for pid in lineup['starters']+lineup['bench']:
                r=by_id[pid]
                role = 'XI' if pid in lineup['starters'] else ('Bænk GK' if r['position']==1 else f"Bænk {lineup['bench'].index(pid)}")
                if pid==lineup['captain']:role+=' · anfører'
                elif pid==lineup['vice_captain']:role+=' · vice'
                records.append(dict(Spiller=r['name'],Rolle=role,**{'Pris £m':r['price']/10,
                    'Forv. minutter':round(r['expected_minutes'],1),'xP':round(r['xp'],3),
                    'DNP %':round(100*r['p_no_play'],1) if r.get('fixture_ids') else None,
                    'Holdbidrag':round(team_contribution[pid]['total'],2) if pid in team_contribution else None,
                    'Kampe':len(r['fixture_ids']),'Fallback':r['fallbacks']}))
            st.dataframe(pd.DataFrame(records),hide_index=True)
            st.caption('Holdbidrag er fra uafhængige evalueringsscenarier med denne faste XI, autosubs og vice; '
                       'spillerens xP vises uden rollen i holdet. Et DNP kan udløse autosub, et kort indhop kan blokere den.')
    with st.expander('Datagrundlag, odds-dækning og antagelser'):
        st.write(f"Beregnet: {forecast['forecast_origin_at']} · officielle data: {forecast['source_available_at']}")
        st.write(f"Dataversion: {forecast['snapshot_id']} · model: {forecast['model_version']}")
        st.write(f"{forecast['draws']} scenarier · seed {forecast['seed']}")
        st.caption('Forbedring måles mod dit uændrede hold. Målværdi og simulerede holdpoint kommer fra separate scenarier; solver/gap gælder kandidatsøgningen.')
        if forecast.get('set_piece_config'):
            st.warning('Gemte dødboldsantagelser – følsomhedsscenarie, ikke kalibrerede frekvenser.')
            st.json(dict(config=forecast['set_piece_config'],source=forecast.get('set_piece_source')))
        from fpl_model.ui.bonus import bonus_notice
        bonus_notice(forecast.get('bonus_config'),forecast.get('bonus_training'))
        if forecast.get('assist_config'):
            st.caption('Eksperiment: fælles FPL-assistkorrektion; alle øvrige pointkomponenter er uændrede.')
            st.json(forecast.get('assist_training',{}))
        if forecast.get('season_prior_config'):
            st.caption('Eksperiment: sidste sæsons spiller-xG/xA som svagt prior; spilletid og bonus uændret. Ukendt historik giver positions-fallback.')
            st.json(forecast['season_prior_config'])
        st.write('Tilgængelighedspolitik:',forecast.get('availability_policy','current_availability_held_constant'))
        st.write('Manuelle antagelser:',forecast.get('availability_assumptions',[]))
        st.write('Scenarieantagelser:',forecast.get('derived_availability_assumptions',[]))
        st.caption('Fremtidig tilgængelighed er en antagelse. Fremtidige priser holdes faste; kampplanen kan ændre sig.')
        if forecast['unassigned_fixture_ids'] or forecast['undated_fixture_ids']:
            st.warning('Kampplanen har uafklarede runder/tider. Ikke tildelte kampe er ikke placeret ved gæt.')
            st.write(dict(uden_GW=forecast['unassigned_fixture_ids'],uden_tid=forecast['undated_fixture_ids']))
        for event,coverage in report['odds_coverage'].items():
            if coverage is None:
                st.write(f'GW{event}: uden odds. Model: {forecast.get("model_version","baseline")}.')
            else:
                st.write(f"GW{event}: {coverage['usable']}/{coverage['expected_fixtures']} med odds · {coverage['bookmaker']}")
                st.caption(f"Hentet/available_at: {coverage['source'].get('available_at','ukendt')}. Præcis publikationstid ukendt.")
                st.dataframe(pd.DataFrame(coverage['fixtures']),hide_index=True)
        for limitation in report['limitations']:
            st.caption(limitation)
    st.download_button('Download transferforslag (JSON)',json.dumps(report,ensure_ascii=False,indent=2),
                       file_name='transferforslag.json',mime='application/json')


def _saved_report_picker(root, state_prefix):
    """Saved reports stay readable even when fresh inputs have no valid deadline."""
    with st.expander('Åbn tidligere transferforslag'):
        saved=sorted((root/'artifacts/transfers').glob('*/report.json'),reverse=True)
        if not saved:
            st.caption('Ingen gemte transferforslag endnu.')
            return
        path=st.selectbox('Gemt sammenligning',saved,
                          format_func=lambda p:f'{saved.index(p)+1}. {saved_comparison_option(p)}')
        if st.button('Åbn gemt sammenligning'):
            try:
                st.session_state.update({state_prefix+'transfer_result':json.loads(path.read_text()),
                    state_prefix+'transfer_signature':None,
                    state_prefix+'transfer_output':str(path.parent)})
            except (ValueError,OSError) as exc:
                st.error(f'Gemt forslag kunne ikke åbnes ({type(exc).__name__}).')


def render(*, experimental_mode=False):
    state_prefix='lab_' if experimental_mode else ''
    guest=guest_mode()
    st.html('<div class="lab-kicker">FPL LAB · HOLDPLANLÆGGER</div>')
    st.title('Transferlaboratorium' if experimental_mode else 'Mit hold · næste træk')
    if not experimental_mode:
        st.caption('Standardprognose')
    player_detail_slot=st.container()
    if guest:
        st.caption('Dit hold gemmes kun i denne session. Download det for at beholde det.')
    active=None
    historical=False
    if guest:
        try:
            active=read_active_public_data(LOCAL_ROOT/'data/raw',LOCAL_ROOT/'artifacts/public_data')
        except ValueError:
            st.error('Der er endnu ikke publiceret et verificeret datagrundlag til gæster. Prøv igen senere.')
            return
        chosen=active['context_path']
        history=active['history_path']
        paths=[chosen]
    else:
        try:
            paths = prototype_data.snapshot_paths(LOCAL_ROOT/'data/raw')
        except (SnapshotError,OSError,ValueError,KeyError) as exc:
            st.error(f'Lokale data kunne ikke verificeres. Ingen nyere data er valgt: {exc}')
            return
        if not paths:
            st.error('Intet officielt snapshot. Brug den eksisterende indsamling først.');return
        # Only an explicit historical choice pins browsing. Old session choices
        # and refresh callbacks must not govern ordinary local reruns.
        st.session_state.pop('pending_official_snapshot_choice',None)
        with st.sidebar.expander('Avanceret · historiske data'):
            historical=st.checkbox('Brug historisk datagrundlag',key='use_historical_official_data')
            if historical:
                pinned=st.session_state.get('historical_official_snapshot_choice')
                options=paths if pinned is None or pinned in paths else [pinned,*paths]
                chosen=st.selectbox('Historisk datagrundlag',options,
                    index=options.index(pinned) if pinned in options else 0,
                    format_func=snapshot_option,key='historical_official_snapshot_choice')
        if historical:
            st.warning('Historisk visning · datagrundlaget er låst til dit valg. '
                       'Nye lokale data vælges først, når historisk visning slås fra.')
        else:
            chosen=paths[0]
            st.caption('Seneste brugbare lokale data · følger nye lokale versioner ved genvisning.')
    failures=[]
    candidates=[chosen] if guest or historical else paths
    for candidate in candidates:
        try:
            manifest=candidate/'manifest.json'
            season=(json.loads(manifest.read_text()).get('run_metadata',{}).get('season','2026-2027')
                    if manifest.exists() else '2026-2027')
            if guest:
                pair_history=history
                loaded=_load_data(str(candidate),_manifest_stamp(candidate),
                                  str(history),_manifest_stamp(history),season)
            else:
                pair_history,loaded,skipped=_load_local_choice(paths,candidate,season,
                    allow_history_fallback=not historical)
                failures.extend(skipped)
        except (SnapshotError,OSError,ValueError,KeyError,TypeError) as exc:
            failures.append((candidate,str(exc)))
            if guest or historical:
                st.error(str(exc));return
        else:
            chosen,history,data=candidate,pair_history,loaded
            break
    else:
        st.error('Intet brugbart lokalt datagrundlag. '+ '; '.join(
            f'{_capture_time(p)}: {message}' for p,message in failures))
        return
    for failed,message in failures:
        st.warning(f'Nyere lokalt datagrundlag hentet {_capture_time(failed)} '
                   f'kunne ikke bruges: {message}. Viser kontekst hentet '
                   f'{friendly_time(data["as_of_at"])}; historikkens hentetid fremgår nedenfor.')
    now = datetime.now(timezone.utc)
    pool = {p['id']:p for p in data['players']}
    clubs = {t['id']:t.get('short_name',t.get('name',str(t['id']))) for t in data['teams']}
    media_by_id = official_media(data['players'], data['teams'])
    labels = {i:f"{p['web_name']} · {clubs[p['team']]} · #{i}" for i,p in pool.items()}
    season = data.get('season','2026-2027')
    profile_path = None if guest else LOCAL_ROOT/'data/processed/my_team.json'
    if 'team_draft' not in st.session_state:
        try:
            _reset_editor(load_profile(profile_path) if profile_path and profile_path.exists() else {})
        except (OSError,ValueError,KeyError) as exc:
            st.error(f'Gemt hold kunne ikke åbnes: {exc}');_reset_editor({})
    next_deadlines=[e for e in data['events'] if utc(e['deadline_time'])>now]
    nearest=min(next_deadlines,key=lambda e:e['id']) if next_deadlines else None
    st.html('<div class="lab-context"><span>OFFICIELLE DATA · '+friendly_time(data['as_of_at'])+
            '</span><span>'+(f'GW{nearest["id"]} · deadline {friendly_time(nearest["deadline_time"])}'
                          if nearest else 'Ingen kommende deadline')+'</span></div>')
    decision_slot=st.empty() if not experimental_mode else None
    st.subheader('1. Dit hold')
    render_import(data,LOCAL_ROOT,_reset_editor,guest=guest)
    reconciled,changed=reconcile_sale_prices(st.session_state['team_draft'],data['players'])
    if changed:
        # New local prices correct saved sale estimates, while unsaved bank,
        # squad and chip choices stay in their mounted widgets.
        st.session_state['team_draft']=reconciled
        for key,player_id in list(st.session_state.items()):
            if key.startswith('owned_id_') and player_id in changed:
                sale_key='owned_sale_'+key.removeprefix('owned_id_')
                sale=st.session_state.get(sale_key)
                maximum_sale=pool[player_id]['now_cost']/10
                if sale is not None and sale>maximum_sale:
                    st.session_state[sale_key]=maximum_sale
        st.session_state['sale_adjusted_ids']=changed
    if st.session_state.get('sale_adjusted_ids'):
        count=len(st.session_state['sale_adjusted_ids'])
        st.warning(f"{count} gemt" + (' salgsværdi oversteg ' if count==1 else 'e salgsværdier oversteg ') +
                   'den aktuelle listepris. Kun kladden er rettet, og beløbene er markeret som estimater; '
                   'beregnet bank kan være for høj. Kontrollér dem i FPL før du gemmer eller følger transferforslag.')
    if guest:
        uploaded=st.file_uploader('Indlæs tidligere downloadet hold (JSON)',type=['json'],max_upload_size=1)
        if uploaded is not None and st.button('Brug uploadet hold'):
            try:
                if uploaded.size > 64 * 1024:
                    raise ValueError('Holdfilen er for stor (maksimalt 64 KB).')
                restored=parse_guest_profile_bytes(uploaded.getvalue())
                validate_profile(restored,data['players'],season=season)
                _reset_editor(restored)
                st.rerun()
            except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
                st.error(f'Holdfilen kunne ikke bruges: {exc}')
    age = (now-utc(data['as_of_at'])).total_seconds()/3600
    history_at=data.get('input_sources',{}).get('history',{}).get('available_at',data['as_of_at'])
    history_gap=data.get('coverage',{}).get('history_refresh_required',False)
    st.caption(f"Priser og status hentet {friendly_time(data['as_of_at'])} · "
               f"spillerhistorik hentet {friendly_time(history_at)} · " +
               ('Standardprognose uden odds' if not experimental_mode else 'Valgt forsøgsmodel nedenfor'))
    with st.expander('Data og hentetider'):
        st.write(f"Spillerpriser, status og kampplan: **{friendly_time(data['as_of_at'])}**")
        st.write(f"Kampvis historik: **{friendly_time(history_at)}**")
        st.caption('Begge tider er dansk tid. Hentning sker kun, når du vælger det. '
                   'Normal visning følger nye lokale data ved genvisning.')
        st.caption(f"Kontekst {age:.0f} timer gammel · historik {((now-utc(history_at)).total_seconds()/3600):.0f} timer gammel")
        st.caption('Teknisk reference')
        st.code(f'Kontekst: {chosen.name}\nHistorik: {history.name}' +
                (f"\nPublicering: {active['publication_id']}" if active else ''))
        if failures:
            st.code('Fravalgte lokale kilder:\n'+'\n'.join(
                f'{path.name}: {message}' for path,message in failures))
        if active:st.caption(f"Kontrolleret: {active.get('checked_at','ukendt')}")
    last_refresh=st.session_state.pop('last_official_refresh',None)
    if last_refresh:
        if last_refresh['status']=='context_only':
            st.success('Kontekst opdateret. Kampvis historik kunne genbruges uden nye spillerforespørgsler.')
        elif last_refresh['status']=='history_complete':
            st.success('Kontekst og hele spillerhistorikken er opdateret i nye snapshots.')
        else:
            st.warning('Spillerhistorikken blev kun delvist hentet. Det nye kontekstsnapshot er bevaret. '
                       'Datastatus nedenfor viser, om en foreløbig beregning kan vælges.')
    last_error=st.session_state.pop('last_official_refresh_error',None)
    if last_error:st.error(f'Historikopdatering mislykkedes ({last_error}). Den nye kontekst er bevaret; gamle historikker bruges ikke som nye labels.')
    if not guest and st.button('Hent seneste data'):
        bar=st.progress(0.0)
        status=st.empty()
        def progress(row):
            stage=row['stage']
            if stage=='context':
                st.session_state['pending_official_snapshot_choice']=row['context_snapshot']
                status.info('Ny officiel kontekst gemt. Kontrollerer, om kampvis historik skal opdateres …')
            elif stage=='history':
                status.info('Nye/ændrede kampe kræver spillerhistorik. Henter hele den aktuelle spillerpulje skånsomt …')
            elif stage=='player':
                bar.progress(row['completed']/row['total'])
                status.caption(f"Spillere: {row['completed']}/{row['total']} · seneste svar: {row['status']}")
        try:
            result=quick_refresh.refresh_official_data(LOCAL_ROOT/'data/raw',season=season,
                known_paths=paths,progress=progress)
            st.session_state['pending_official_snapshot_choice']=result['selected_snapshot']
            st.session_state['last_official_refresh']=result
            st.rerun()
        except (FPLSourceError,SnapshotError,OSError,ValueError) as exc:
            if st.session_state.get('pending_official_snapshot_choice'):
                st.session_state['last_official_refresh_error']=type(exc).__name__
                st.rerun()
            st.error(f'Opdatering mislykkedes ({type(exc).__name__}); det valgte datagrundlag er uændret.')
    if history_gap and not guest:
        st.caption('Efter en spillet kamp kræves fuld kampvis historik. Det kan tage flere minutter.')
        if st.button('Hent fuld spillerhistorik'):
            from fpl_model.full_player_capture import capture_all_players
            progress_bar=st.progress(0.0)
            progress_text=st.empty()
            def progress(row):
                progress_bar.progress(row['completed']/row['total'])
                progress_text.caption(f"Spillere: {row['completed']}/{row['total']} · seneste svar: {row['status']}")
            try:
                with st.spinner('Henter kampvis historik for hele spillerpuljen…'):
                    fresh=capture_all_players(LOCAL_ROOT/'data/raw',season=season,progress=progress)
                st.session_state['pending_official_snapshot_choice']=fresh
                st.rerun()
            except (FPLSourceError,SnapshotError,OSError,ValueError) as exc:
                st.error(f'Fuld opdatering mislykkedes ({type(exc).__name__}); rådata fra forsøget bevares lokalt.')
    readiness=assess_deadline_readiness(data,now)
    if readiness['status']=='ready':
        st.success(f"Klar til GW{readiness['event']} · deadline {friendly_time(readiness['deadline_at'])} dansk tid")
    elif readiness['status']=='attention':
        st.warning(f"Kontrollér data før GW{readiness['event']}: {readiness_message(readiness['reasons'])}.")
    elif readiness['new_forecast_status']=='limited':
        missing_count=len(readiness['missing_player_ids'])
        message=(f"Ufuldstændige data før GW{readiness['event']}: "
                 f"{readiness_message(readiness['limited_reasons'])}.")
        if missing_count:
            message+=f' {missing_count} spillerhistorik' + ('ker' if missing_count!=1 else '') + ' mangler.'
        if readiness['quarantined_rows']:
            message+=f" {readiness['quarantined_rows']} historikrækker i karantæne."
        st.warning(message)
        st.caption('Hent seneste data for fuld dækning, eller vælg en tydeligt foreløbig beregning.')
    else:
        message=f"Ikke klar til nye forslag: {readiness_message(readiness['reasons'])}."
        if readiness['quarantined_rows']:
            message+=f" {readiness['quarantined_rows']} historikrækker i karantæne."
        st.error(message)
    limited_acceptance=False
    if readiness['new_forecast_status']=='limited':
        limited_acceptance=st.checkbox('Beregn med ufuldstændige data (foreløbig)',
            key=f"{state_prefix}limited_input_{data['snapshot_id']}_{history.name}")
        st.caption('Manglende kamprækker tælles ikke som DNP. Spillere uden et komplet observeret '
                   'historikvindue får markeret model-fallback; gamle rækker bruges ikke som nye labels.')
    can_calculate=(readiness['new_forecast_status']=='ready' or
                   readiness['new_forecast_status']=='limited' and limited_acceptance)
    if history_gap:
        coverage=data['coverage']
        st.warning('Spillerhistorikken mangler nye eller ændrede oplysninger. '
                   'En beregning før fuld opdatering er foreløbig.')
    if readiness['limited_reasons']:
        coverage=data.get('coverage') or {}
        with st.expander('Hvilke data mangler?'):
            st.write(dict(begyndte_kampe=coverage.get('newly_started_fixture_ids',[]),
                          afsluttede_kampe=coverage.get('newly_finished_fixture_ids',[]),
                          reviderede_resultater=coverage.get('revised_result_fixture_ids',[]),
                          nye_spillere=coverage.get('new_player_ids_without_history',[]),
                          spillere_uden_svar=[labels.get(i,str(i)) for i in readiness['missing_player_ids']],
                          karantænerækker=coverage.get('quarantined_rows',0),
                          karantænespillere=[labels.get(i,str(i)) for i in readiness['quarantined_player_ids']],
                          igangværende_kampe=readiness['in_progress_fixture_ids']))
            for reason,count in readiness['quarantine_reason_counts'].items():
                st.caption(f'{quarantine_reason_label(reason)}: {count}')
    overview = st.container()
    with st.expander('Redigér bank og transfers',
                     expanded=st.session_state.pop('editor_expand_once',False) or not bool(st.session_state['team_draft'].get('players'))):
        c1,c2,c3 = st.columns(3)
        if not guest and c1.button('Genindlæs gemt hold',disabled=not profile_path.exists()):
            try:_reset_editor(load_profile(profile_path))
            except (OSError,ValueError,KeyError) as exc:st.error(str(exc))
        if c2.button('Indlæs eksempelhold fra billedet'):
            try:_reset_editor(_example(data['players'],season))
            except ValueError as exc:st.error(str(exc))
        if c3.button('Nyt tomt hold'):
            _reset_editor({})
        draft = st.session_state['team_draft']
        if draft.get('season',season)!=season:
            st.error('Det gemte hold er fra en anden sæson. Vælg Nyt tomt hold og indtast det aktuelle hold; gemte data ændres først ved Gem hold.')
        missing = [r['player_id'] for r in draft.get('players',[]) if r['player_id'] not in pool]
        if missing:st.warning(f'Gemte spiller-ID’er findes ikke i snapshot: {missing}. Vælg dem eksplicit igen.')
        cols=st.columns(3)
        st.session_state.setdefault('owned_bank',draft['bank']/10 if draft.get('bank') is not None else None)
        st.session_state.setdefault('owned_free',draft.get('free_transfers'))
        st.session_state.setdefault('owned_made',draft.get('transfers_made'))
        bank=cols[0].number_input('Bank (£m)',min_value=0.,step=.1,
                                 value=None,key='owned_bank')
        free=cols[1].number_input('Resterende gratis transfers',min_value=0,max_value=5,
                                 value=None,step=1,key='owned_free')
        made=cols[2].number_input('Transfers allerede foretaget denne GW',min_value=0,max_value=20,
                                 value=None,step=1,key='owned_made')
        profile=None; error=None
        from fpl_model.ui.chips import render_chip_inventory,render_chip_schedule
        chip_fields={}
        try:chip_fields=render_chip_inventory(draft,data)
        except (ValueError,TypeError,KeyError) as exc:error=str(exc);st.error('Chipoplysninger: '+str(exc))
        selected=[]; slot=0
        with st.expander('Ret spillere og salgsværdier',expanded=not bool(draft.get('players'))):
            st.caption('FPL’s offentlige holdimport oplyser ikke dine individuelle salgsværdier. '
                       'Listepriser kan bruges som markerede estimater; ret især spillere, du overvejer at sælge.')
            for pos,(name,count) in POSITIONS.items():
                entries = [r for r in draft.get('players',[]) if pool.get(r['player_id'],{}).get('element_type')==pos]
                st.write(f'**{name} · {count} spillere**')
                for j in range(count):
                    entry = entries[j] if j<len(entries) else {}
                    choices = [None]+sorted([i for i,p in pool.items() if p['element_type']==pos],key=lambda i: labels[i])
                    cols=st.columns([3,1])
                    # Explicit state sends the reset to mounted browser widgets; merely
                    # changing a keyed widget's default leaves its visible value stale.
                    st.session_state.setdefault(f'owned_id_{slot}',entry.get('player_id'))
                    value=entry.get('selling_price')
                    st.session_state.setdefault(f'owned_sale_{slot}',value/10 if value is not None else None)
                    pid=cols[0].selectbox(f'{name} {j+1}',choices,
                                          format_func=lambda i:labels.get(i,'Vælg spiller'),key=f'owned_id_{slot}',
                                          on_change=_clear_sale,args=(slot,))
                    sale=cols[1].number_input(f'Salgsværdi {name.lower()} {j+1} (£m)',min_value=0.,step=.1,
                                              value=None,key=f'owned_sale_{slot}')
                    selected.append((pid,sale));slot+=1
        try:
            if free is None or made is None:raise ValueError('Angiv resterende gratis transfers og antal transfers allerede foretaget denne GW.')
            estimated=set(draft.get('price_estimate_ids',[]))
            original_sales={p['player_id']:p['selling_price'] for p in draft.get('players',[])}
            current_sales=[dict(player_id=i,selling_price=money(s)) for i,s in selected]
            estimated=sorted(p['player_id'] for p in current_sales if p['player_id'] in estimated and
                             p['selling_price']==original_sales.get(p['player_id']))
            profile=dict(schema_version=1,season=draft.get('season',season),players=current_sales,
                         bank=money(bank),free_transfers=int(free),transfers_made=int(made),**chip_fields)
            if estimated:profile['price_estimate_ids']=estimated
            validate_profile(profile,data['players'],season=season)
            if draft.get('import_provenance'):profile['import_provenance']=draft['import_provenance']
        except (ValueError,TypeError,KeyError) as exc:error=str(exc)
        save_clicked=st.button('Gem hold')
        if save_clicked:
            if error:st.error(error)
            else:
                if not guest:save_profile(profile,profile_path)
                st.session_state['team_draft']=profile
                st.session_state.pop('sale_adjusted_ids',None)
                st.success('Holdet er gemt i denne session.' if guest else
                           'Holdet er gemt lokalt. Forslag ændrer ikke dit hold automatisk.')
    if guest and not error:
        st.download_button('Download mit hold (JSON)',
            json.dumps(profile,ensure_ascii=False,indent=2,allow_nan=False),
            file_name='mit-fpl-hold.json',mime='application/json')
    with overview:
        future_events=[e for e in data['events'] if utc(e['deadline_time'])>now]
        next_event=min(future_events,key=lambda e:e['id']) if future_events else None
        ids=list(dict.fromkeys(i for i,_ in selected if i in pool))
        summary_metrics([
            ('Bank',f'£{bank:.1f}m' if bank is not None else 'Udfyld','Dit transferbudget'),
            ('Gratis transfers',str(free) if free is not None else 'Udfyld','Til rådighed nu'),
            ('Din trup',f'{len(ids)} / 15','Spillere valgt')])
        st.subheader('Dit holdoverblik')
        st.caption('Trup efter position · anbefalet XI vises i forslaget')
        if ids:
            cards=[]
            for i in ids:
                p=pool[i];chance=p.get('chance_of_playing_next_round')
                flag=('Tvivl' if p.get('status')=='d' else 'Status '+str(p['status'])) if p.get('status') not in (None,'a') else ''
                if flag and chance is not None:flag+=f' · {chance}%'
                cards.append(dict(id=i,name=p['web_name'],position=p['element_type'],
                    detail=f"{clubs[p['team']]} · køb £{p['now_cost']/10:.1f}m",flag=flag,
                    **media_by_id.get(i,{})))
            squad_view=st.radio('Holdvisning',['Liste','Bane'],horizontal=True,key='squad_view')
            st.html(team_html(cards,view=squad_view,clickable=True))
            st.caption('Tryk på en spiller for at se prognose og sammenligne med andre.')
            if squad_view=='Bane':
                st.caption('Skub banen vandret på en smal skærm for at se alle spillere.')
            if any(card['flag'] for card in cards):
                st.caption('Statusmærker kommer fra FPL og er ikke modellens startchance.')
        else:
            st.info('Start med dit hold-ID eller åbn Redigér bank og transfers for at vælge spillere manuelt.')
        if profile and profile.get('price_estimate_ids') and not st.session_state.get('sale_adjusted_ids'):
            count=len(profile['price_estimate_ids'])
            st.warning(f"{count} salgsværdi" + (' er et estimat. ' if count==1 else 'er er estimater. ') +
                       'Forslagets bank kan være for høj; verificér salgsværdier for udgående spillere i FPL.')
        if error:st.caption('Holdet mangler gyldige oplysninger. Åbn Redigér bank og transfers før du beregner forslag.')
    st.subheader('2. Planlæg')
    future=[e['id'] for e in data['events'] if utc(e['deadline_time'])>now]
    if not future:
        st.error('Datagrundlaget har ingen fremtidig officiel deadline. Opdatér data før en ny beregning.')
        if not guest:_saved_report_picker(LOCAL_ROOT,state_prefix)
        if state_prefix+'transfer_result' in st.session_state:
            st.warning('Viser et tidligere gemt forslag med datagrundlaget og tidspunktet fra den oprindelige beregning.')
            show_report(st.session_state[state_prefix+'transfer_result'],
                        compact=not experimental_mode,media_by_id=media_by_id)
        return
    start=min(future)
    st.write(f'Vi starter i **GW{start}**. Hvor mange runder vil du planlægge?')
    available=1
    while available<4 and start+available in future:
        available+=1
    horizon=st.selectbox('Horisont (GWs)',list(range(1,available+1)))
    events=list(range(start,start+horizon))
    st.caption('Standard: vi kan vente med transfers til en senere runde. Ingen pointfradrag. Flere valg nedenfor.')
    with st.expander('Tilpas transferplan, chips og antagelser', expanded=experimental_mode):
        chip_plan=render_chip_schedule(profile,events,data,now.isoformat()) if profile and not error else {}
        mode=st.selectbox('Planlægning',['Transfers uge for uge','Alle transfers nu'])
        sequential=mode=='Transfers uge for uge'
        cols=st.columns(2)
        maximum=cols[0].number_input('Maksimalt antal transfers pr. GW' if sequential else 'Maksimalt antal nye transfers',min_value=0,max_value=15,value=2 if sequential else 1,step=1)
        hits=cols[1].checkbox('Tillad pointfradrag (−4 pr. ekstra transfer)',value=False)
        owned=[i for i,_ in selected if i in pool]
        locked=st.multiselect('Behold disse spillere',sorted(set(owned)),format_func=labels.get)
        excluded=st.multiselect('Udeluk fra forslag',sorted(pool,key=labels.get),format_func=labels.get)
        st.caption('Behold/udeluk gælder hele horisonten.')
        total=st.number_input('Maksimalt antal transfers i hele horisonten',min_value=0,max_value=60,value=4,step=1) if sequential else int(maximum)
        availability_policy='hold_current'
        if len(events)>1:
            availability_policy=st.selectbox('Tilgængelighed i senere GWs',
                ['hold_current','short_doubt_next_gw'],index=1,format_func=lambda x:
                'Forsigtig: viderefør nuværende FPL-faktor' if x=='hold_current' else
                'Scenarie: 75%-tvivl ophører efter første GW')
            if availability_policy=='short_doubt_next_gw':
                st.warning(f'Planlægningsantagelse: status d + 75% bevares i GW{events[0]}, men får faktor 1 fra GW{events[1]}. '
                           'Det er ikke en verificeret raskmelding eller 100% startchance. Andre skade-/karantæneflag ændres ikke. '
                           'Sammenhold med den forsigtige indstilling før transfers.')
        assumptions,sensitivity=availability_controls(data,owned,events,labels,allow_sensitivity=sequential)
        from fpl_model.ui.forecast_controls import standard_forecast_settings,render_experimental_forecast_controls
        settings=(render_experimental_forecast_controls(data,events,labels,paths,LOCAL_ROOT)
                  if experimental_mode else standard_forecast_settings())
        model=settings['model']
        experimental=settings['experimental']
        set_pieces=settings['set_pieces']
        role_only=settings['role_only']
        uses_odds=settings['uses_odds']
        evolution=settings['evolution']
        roles=settings['roles']
        odds_scope=settings['odds_scope']
        set_piece_config=settings['set_piece_config']
        set_piece_path=settings['set_piece_path']
        bonus_config=settings['bonus_config']
        season_prior_config=settings['season_prior_config']
        assist_config=settings['assist_config']
        odds_path=settings['odds_path']
        if uses_odds:
            from fpl_model.defensive_odds import build_coverage
            try:
                odds_rows,odds_source=(load_odds(odds_path,'the_odds_api') if odds_path else
                    ([],dict(source='the_odds_api',available_at=now.isoformat(),
                             retrieved_at=now.isoformat(),failure='no_saved_odds')))
                for planned_event in events:
                    preview=build_coverage(data,odds_rows,odds_source,planned_event,
                                           BaselineConfig(),now.isoformat())
                    st.caption(f"Odds-dækning GW{planned_event}: {preview['usable']}/{preview['expected_fixtures']} "
                               f"kampe · {preview['bookmaker']} · observation {odds_source.get('available_at','ukendt')}")
                    if preview['usable']<preview['expected_fixtures']:
                        reasons=dict(Counter(f['reason'] for f in preview['fixtures'] if f['status']!='odds'))
                        st.warning(f'Kampe uden godkendte odds bruger markeret baseline-fallback: {reasons}.')
            except (ValueError,OSError,KeyError) as exc:
                st.error(f'Odds-dækning kunne ikke verificeres ({type(exc).__name__}). Vælg baseline eller et andet gemt snapshot.')
        with st.expander('Beregningsindstillinger og antagelser'):
            draws=st.selectbox('Scenarier',[3000,1000,500] if guest else [3000,1000,500,10000])
            seed=st.number_input('Seed',min_value=0,max_value=2147483647,value=42,step=1)
            st.write('Standardmodellen og priserne bevares. Tilgængelighed følger det valgte scenarie; manuelle GW-antagelser har forrang. '
                     'Chips placeres manuelt. Bænkvægt i kandidatsøgningen: 0,1; Bench Boost værdisætter hele truppen.')
    request=(str(chosen),str(history),data.get('manifest_sha256'),
             json.dumps(data.get('input_sources'),sort_keys=True),tuple(events),model,
             str(odds_path),str(set_piece_config),str(set_piece_path),str(bonus_config),
             str(season_prior_config),str(assist_config),draws,int(seed),availability_policy,
             json.dumps([assumptions,sensitivity,roles],sort_keys=True))
    signature=(request,json.dumps(profile,sort_keys=True),mode,maximum,total,hits,tuple(sorted(locked)),tuple(sorted(excluded)),json.dumps(chip_plan,sort_keys=True))

    def current_bundle(status):
        """One forecast per session request; player view and optimizer share it."""
        if st.session_state.get(state_prefix+'forecast_request')!=request:
            st.session_state[state_prefix+'forecast_request']=request
            st.session_state[state_prefix+'forecast_origin']=now.isoformat()
            st.session_state.pop(state_prefix+'forecast_bundle',None)
        origin=st.session_state[state_prefix+'forecast_origin']
        odds=(load_odds(odds_path,'the_odds_api') if odds_path else
              ([],dict(source='the_odds_api',available_at=origin,retrieved_at=origin,
                       failure='no_saved_odds'))) if uses_odds else None
        set_piece_source=None
        if set_piece_config is not None:
            from fpl_model.set_piece_roles import load_roles
            set_piece_source=load_roles(set_piece_path)
        bundle=st.session_state.get(state_prefix+'forecast_bundle')
        if bundle is None:
            forecast_root=(guest_root() if guest else LOCAL_ROOT)/'artifacts/transfer_forecasts'
            bundle=forecast_bundle(data,events,BaselineConfig(),origin_at=origin,
                cache_root=forecast_root,draws=draws,seed=int(seed),odds=odds,progress=status.info,
                availability=scenario_records(assumptions,sensitivity,events,origin,'a'),
                availability_policy=availability_policy,odds_scope=odds_scope,evolution=evolution,
                role_assumptions=[dict(r,observed_at=origin) for r in roles],
                set_piece_config=set_piece_config,set_piece_source=set_piece_source,
                bonus_config=bonus_config,season_prior_config=season_prior_config,
                assist_config=assist_config)
            st.session_state[state_prefix+'forecast_bundle']=bundle
        return bundle,origin,odds,set_piece_source

    active_report=st.session_state.get(state_prefix+'transfer_result')
    report_ids=({player_id for plan in active_report['packages']
                 for lineup in plan.get('lineups',{}).values()
                 for player_id in lineup['squad']} if active_report else set())
    selected_id=selected_owned_id(st.query_params.get('player_id'),set(ids)|report_ids)
    if selected_id is not None:
        with player_detail_slot:
            report_names=({r['player_id']:r['name'] for r in
                           next(iter(active_report['players_by_event'].values()),[])}
                          if active_report else {})
            player_name=report_names.get(selected_id) or pool.get(selected_id,{}).get('web_name',str(selected_id))
            st.subheader(f'Spillerprognose · {player_name}')
            if not can_calculate:
                st.warning('Spillerprognosen kræver en sikker datakilde eller dit udtrykkelige valg '
                           'af foreløbig beregning. Se datastatus ovenfor.')
            else:
                permit=None
                try:
                    if guest and st.session_state.get(state_prefix+'forecast_bundle') is None:
                        permit=claim_guest_job('comparison')
                    status=st.empty()
                    if active_report is not None:
                        forecast_root=(guest_root() if guest else LOCAL_ROOT)/'artifacts/transfer_forecasts'
                        bundle=bundle_for_report(active_report,
                            st.session_state.get(state_prefix+'forecast_bundle'),forecast_root)
                        detail_event=start if start in bundle['rows'] else min(bundle['rows'])
                    else:
                        bundle,_,_,_=current_bundle(status)
                        detail_event=start
                    status.empty()
                    detail_lookup={r['player_id']:r for r in bundle['rows'][detail_event]}
                    if selected_id not in detail_lookup:
                        raise ValueError('Spilleren findes ikke i den viste prognoses datagrundlag.')
                    detail_labels={i:row['name'] for i,row in detail_lookup.items()}
                    candidate_ids=[i for i in detail_lookup if i!=selected_id]
                    defaults=[i for i in ids if i in candidate_ids and
                              detail_lookup[i]['position']==detail_lookup[selected_id]['position']][:2]
                    peers=st.multiselect('Sammenlign med andre spillere',
                        sorted(candidate_ids,key=detail_labels.get),default=defaults,
                        format_func=detail_labels.get,max_selections=3,key=f'player_compare_{selected_id}')
                    rows=comparison_rows(bundle,detail_event,selected_id,peers)
                    selected_row=rows[0]
                    if active_report is not None:
                        st.caption('Spillerkortet bruger den viste gemte prognose og dens oprindelige indstillinger.')
                    if readiness['new_forecast_status']=='limited':
                        st.warning('Foreløbig prognose: den viste historik kan være ufuldstændig. '
                                   'Kontrollér markerede fallbacks før du handler.')
                    elif readiness['status']!='ready':
                        st.warning('Kontrollér datagrundlagets alder før du følger forslaget.')
                    observed=bundle['metadata'].get('source_available_at')
                    st.caption(f"GW{detail_event} · {bundle['metadata']['model_version']} · "
                               f"{bundle['metadata']['draws']:,} scenarier · data hentet "
                               f"{friendly_time(observed) if observed else 'tid ukendt'}")
                    metrics=st.columns(4)
                    for col,label,value in zip(metrics,['Forventede point','P10 / median / P90',
                            'Forventede minutter','Ingen spilletid'],[
                            f"{selected_row['xp']:.2f}",
                            f"{selected_row['p10']:.0f} / {selected_row['p50']:.0f} / {selected_row['p90']:.0f}",
                            f"{selected_row['expected_minutes']:.0f}",
                            f"{selected_row['p_no_play']:.0%}" if selected_row['fixture_ids'] else 'Blank GW']):
                        col.metric(label,value)
                    comparison=pd.DataFrame([dict(Spiller=r['name'],Klub=clubs.get(r['team_id'],'?'),
                        Position=POSITIONS[r['position']][0],**{'Pris £m':r['price']/10 if r['price'] is not None else None,
                        'xP':round(r['xp'],2),'P10':r['p10'],'Median':r['p50'],'P90':r['p90'],
                        'Forv. minutter':round(r['expected_minutes'],1),
                        'Ingen spilletid %':round(100*r['p_no_play'],1) if r['fixture_ids'] else None,
                        'Kampe i GW':len(r['fixture_ids'])}) for r in rows])
                    st.dataframe(comparison,hide_index=True,width='stretch')
                    if detail_event in bundle['planning_scenarios']:
                        distribution=point_distribution(bundle,detail_event,selected_id)
                        st.caption('Pointfordeling for den valgte spiller · foreløbig simulation, ikke dokumenteret kalibrerede sandsynligheder.')
                        st.bar_chart(pd.DataFrame(distribution,columns=['Point','Sandsynlighed']).set_index('Point'))
                    else:
                        st.caption('Scenariefordelingen er ikke gemt for dette ældre forslag. Kun de gemte nøgletal vises.')
                    explanation=bundle['explanations'].get(detail_event,{})
                    explanation=explanation.get(selected_id) or explanation.get(str(selected_id),{})
                    if selected_row.get('p_start') is not None and explanation.get('p_sub') is not None:
                        start_probability=selected_row['p_start']
                        sub_probability=explanation['p_sub']
                        st.caption(f"Startchance pr. kamp {start_probability:.0%} · "
                                   f"indhopchance {sub_probability:.0%} · "
                                   f"DNP pr. kamp {1-start_probability-sub_probability:.0%} · "
                                   f"betingede minutter: start {explanation['start_minutes']:.0f}, "
                                   f"indhop {explanation['sub_minutes']:.0f}. "
                                   'Ved dobbelt GW gælder disse sandsynligheder hver kamp; ovenstående xP og minutter summeres over GW.')
                    components=explanation.get('point_components',{})
                    if components:
                        st.caption('Forventede point efter komponent · samme simulation')
                        st.dataframe(pd.DataFrame([dict(Komponent=name,Point=round(value,2))
                            for name,value in components.items()]),hide_index=True)
                    basis_names={'player_fixture_history':'kampvis historik',
                                 'season_aggregates':'sæsonaggregater',
                                 'explicit_priors':'eksplicitte priors'}
                    st.caption(f"Historik: {selected_row['history_rows']} kampe · "
                               f"{basis_names.get(selected_row['basis'],selected_row['basis'])}. "
                               f"Fallback: {selected_row['fallbacks'] or 'ingen'}. "
                               'Prognoserne gælder hele GW’en; ved to kampe kan minutterne overstige 90.')
                except GuestLimitError as exc:st.warning(str(exc))
                except (ValueError,RuntimeError,OSError,KeyError) as exc:
                    st.error(f'Spillerprognosen kunne ikke beregnes: {exc}')
                finally:
                    if permit is not None:permit.release()
    st.subheader('3. Forslag')
    st.caption(f"Vi sammenligner dit uændrede hold med lovlige forslag for GW{events[0]}–{events[-1]}. "
               f"{mode} · højst {int(maximum)} transfers {'pr. GW' if sequential else 'nu'} · "
               f"{'pointfradrag tilladt' if hits else 'ingen pointfradrag'}.")
    if st.button('Sammenlign transferforslag',type='primary',use_container_width=True,
                 disabled=not can_calculate):
        if error:st.error(error)
        else:
            permit=None
            try:
                if chip_plan and not sequential:raise ValueError('Chips kræver Planlægning: Transfers uge for uge.')
                from fpl_model.chips import validate_chip_plan
                validate_chip_plan(chip_plan,profile,events,deadlines={e['id']:e['deadline_time'] for e in data['events']},origin_at=now.isoformat())
                if guest:permit=claim_guest_job('comparison')
                status=st.empty()
                bundle,origin,odds,set_piece_source=current_bundle(status)
                if sequential:
                    report=compare_sequences(bundle,profile,max_per_gw=int(maximum),max_total=int(total),
                                             locked=locked,excluded=excluded,allow_hits=hits,progress=status.info,chip_plan=chip_plan)
                    if sensitivity:
                        report['scenario_label']=f"A · {sensitivity['name']} tilgængelig fra GW{sensitivity['return_a']}"
                        forecast_root=(guest_root() if guest else LOCAL_ROOT)/'artifacts/transfer_forecasts'
                        alternative=forecast_bundle(data,events,BaselineConfig(),origin_at=origin,
                            cache_root=forecast_root,draws=draws,seed=int(seed),odds=odds,
                            progress=status.info,availability=scenario_records(assumptions,sensitivity,events,origin,'b'),availability_policy=availability_policy,odds_scope=odds_scope,evolution=evolution,
                    role_assumptions=[dict(r,observed_at=origin) for r in roles],set_piece_config=set_piece_config,set_piece_source=set_piece_source,bonus_config=bonus_config,season_prior_config=season_prior_config,assist_config=assist_config)
                        report['sensitivity']=compare_sensitivity(report,alternative,progress=status.info,
                            label=f"A: tilgængelig fra GW{sensitivity['return_a']} · B: fra GW{sensitivity['return_b']} · {sensitivity['name']}")
                else:
                    report=compare_packages(bundle,profile,max_transfers=int(maximum),locked=locked,excluded=excluded,
                                            allow_hits=hits,progress=status.info)
                report['input_readiness']=dict(readiness,explicitly_accepted=limited_acceptance)
                output=None if guest else save_report(report,LOCAL_ROOT/'artifacts/transfers')
                st.session_state.update({state_prefix+'transfer_result':report,state_prefix+'transfer_signature':signature,state_prefix+'transfer_output':str(output)})
                status.success('Sammenligningen er klar i denne session. Download den, hvis du vil gemme den.' if guest else
                               'Sammenligningen er gemt. Dit hold er ikke ændret.')
            except GuestLimitError as exc:st.warning(str(exc))
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
            finally:
                if permit is not None:permit.release()
    if not guest:_saved_report_picker(LOCAL_ROOT,state_prefix)
    if state_prefix+'transfer_result' in st.session_state:
        report=st.session_state[state_prefix+'transfer_result']
        stale=st.session_state.get(state_prefix+'transfer_signature')!=signature
        if decision_slot is not None:
            decision=(sequence_decision(report) if report.get('scope')=='transfer_sequences'
                      else immediate_decision(report))
            first=next(iter(report['players_by_event'].values()))
            report_names={r['player_id']:r['name'] for r in first}
            name_list=lambda ids:', '.join(report_names.get(i,str(i)) for i in ids)
            chip=None
            if report.get('scope')=='transfer_sequences':
                from fpl_model.chips import LABELS
                selected_plan=next(p for p in report['packages'] if p['plan_id']==decision['plan_id'])
                chip=LABELS.get(selected_plan['steps'][0].get('chip'))
            else:
                selected_plan=max(report['packages'],key=lambda p:(p['objective'],-p['count']))
            alternatives=alternative_previews(report['packages'],selected_plan)
            decision_slot.html(decision_overview_html(decision,event=decision.get('event',events[0]),
                          names=name_list,stale=stale,chip=chip,alternatives=alternatives,
                          weeks=selected_plan['per_gw'],data_attention=readiness['status']!='ready'))
        if stale:
            st.warning('Viser en gemt beregning med dens oprindelige hold og indstillinger. Kør igen for dine aktuelle valg.')
        show_report(report,compact=not experimental_mode,media_by_id=media_by_id)
    elif decision_slot is not None:
        decision_slot.html(next_step_card_html(
            player_count=len(ids),profile_error=error,
            readiness_status=('limited' if readiness['new_forecast_status']=='limited' else readiness['status']),
            price_estimates=bool(profile and profile.get('price_estimate_ids')) or
                            bool(st.session_state.get('sale_adjusted_ids')),
            can_refresh=not guest))
