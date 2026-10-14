"""Personal-team editor and transfer comparisons. Team import is an explicit action."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from fpl_model.config import ROOT
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import BaselineConfig
from fpl_model.my_team import money, validate_profile, save_profile, load_profile
from fpl_model import prototype_data
from fpl_model import quick_refresh
from fpl_model.data_sources.fpl_api import FPLSourceError
from fpl_model.io import SnapshotError
from fpl_model.odds_comparison import load_odds
from fpl_model.transfer_planner import forecast_bundle, compare_packages, save_report
from fpl_model.sequence_planner import compare_sequences, compare_sensitivity
from fpl_model.ui.strategy import availability_controls, scenario_records, show_sequence_report
from fpl_model.ui.team_import import render_import
from fpl_model.ui.presentation import pitch_html, show_lineup_pitch, transfer_card, summary_metrics

LOCAL_ROOT = ROOT
POSITIONS = {1: ('Målmand',2), 2: ('Forsvarer',5), 3: ('Midtbane',5), 4: ('Angriber',3)}
EXAMPLE_NAMES = ['Verbruggen','Steele','Konsa','De Cuyper','Gvardiol','Ajer','Egan',
                 'Cherki','Rogers','Szoboszlai','B.Fernandes','Slater','Wissa','Haaland','João Pedro']


@st.cache_data(show_spinner=False)
def _load_data(path, manifest_stamp, history_path, history_stamp, season):
    if Path(path).resolve()==Path(history_path).resolve():
        return prototype_data.load_data(Path(path),season=season,include_season_history=True)
    return quick_refresh.load_current_inputs(Path(path),Path(history_path),season=season,
                                             include_season_history=True)


def _reset_editor(profile):
    for key in list(st.session_state):
        if key.startswith('owned_'):
            del st.session_state[key]
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


def show_report(report):
    if report.get('scope')=='transfer_sequences':
        return show_sequence_report(report)
    forecast = report['forecast']
    st.subheader('Transferforslag')
    st.caption(f"Gemt prognose: {forecast['forecast_origin_at']} · officiel kilde observeret {forecast['source_available_at']} · "
               f"{forecast['model_version']} · {forecast['draws']} scenarier · seed {forecast['seed']}")
    st.info('Alle transfers sker nu. Truppen beholdes derefter; XI og anfører vælges separat pr. GW.')
    st.caption('Forbedring måles mod dit uændrede hold med samme opstillingsmetode. '
               'Målværdi inkl. autosubs/vice vælges på planlægningsscenarier; holdpoint evalueres på separate scenarier. '
               'Solver/gap gælder den tilnærmede kandidatsøgning, ikke den samlede transferstrategi.' if report['packages'][0].get('lineup_policy') else
               'Ældre rapport: målværdien bruger en tilnærmet bænkvægt; autosubs indgår i evalueringen.')
    first = next(iter(report['players_by_event'].values()))
    pool = {r['player_id']: r for r in first}
    names = lambda ids: ', '.join(pool[i]['name'] for i in ids) or '—'
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
    index = st.selectbox('Forslag – se opstillinger', options,
                        format_func=lambda i: rows[i]['Forslag'],key='proposal_detail')
    proposal = report['packages'][index]
    transfer_card(rows[index]['Forslag'],names(proposal['out']),names(proposal['in']),proposal['bank_after'],proposal['hits'],proposal['total_gain'])
    st.write('Gratis transfers gennem horisonten (ingen yderligere køb):')
    st.dataframe(pd.DataFrame(proposal['transfer_schedule']).rename(columns={
        'event':'GW','available':'Til rådighed','used':'Gratis brugt','remaining':'Tilbage',
        'next_gw':'Til næste GW','hits':'Pointfradrag'}),hide_index=True)
    st.caption('Opsparing vises som regnskab. Værdien af at vente er ikke fuldt optimeret.')
    st.dataframe(pd.DataFrame(proposal['per_gw']).rename(columns={
        'event':'GW','mean':'Simulerede point, netto','gain':'Gevinst mod behold','objective':'Målværdi, netto',
        'bench_mean':'Autosub-point','hits':'Pointfradrag'}),hide_index=True)
    tabs=st.tabs([f'GW{e}' for e in proposal['lineups']])
    for tab,(event, lineup) in zip(tabs,proposal['lineups'].items()):
        table = report['players_by_event'].get(event) or report['players_by_event'].get(str(event))
        by_id = {r['player_id']:r for r in table}
        with tab, st.expander(f'GW{event} · XI, bænk og anfører', expanded=True):
            show_lineup_pitch(by_id,lineup)
            records = []
            for pid in lineup['starters']+lineup['bench']:
                r=by_id[pid]
                role = 'XI' if pid in lineup['starters'] else ('Bænk GK' if r['position']==1 else f"Bænk {lineup['bench'].index(pid)}")
                if pid==lineup['captain']:role+=' · anfører'
                elif pid==lineup['vice_captain']:role+=' · vice'
                records.append(dict(Spiller=r['name'],Rolle=role,**{'Pris £m':r['price']/10,
                    'Forv. minutter':round(r['expected_minutes'],1),'xP':round(r['xp'],3),
                    'Kampe':len(r['fixture_ids']),'Fallback':r['fallbacks']}))
            st.dataframe(pd.DataFrame(records),hide_index=True)
    with st.expander('Datagrundlag, odds-dækning og antagelser'):
        st.write(f"Snapshot: {forecast['snapshot_id']}")
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


def render(*, experimental_mode=False):
    state_prefix='lab_' if experimental_mode else ''
    st.html('<div class="lab-kicker">FPL LAB / HOLDPLANLÆGGER</div>')
    st.title('Transferlaboratorium' if experimental_mode else 'Mit hold')
    if not experimental_mode:
        st.info('Standardprognose · den eksisterende baseline. Modelvalg og forsøg findes under Analyse og eksperimenter.')
    st.caption('Overblik først. Planlæg dine næste transfers, én gameweek ad gangen.')
    paths = prototype_data.snapshot_paths(LOCAL_ROOT/'data/raw')
    if not paths:
        st.error('Intet officielt snapshot. Brug den eksisterende indsamling først.');return
    pending=st.session_state.pop('pending_official_snapshot_choice',None)
    if pending in paths:
        st.session_state['official_snapshot_choice']=pending
    chosen = st.sidebar.selectbox('Officielt datagrundlag',paths,index=0,
                                  format_func=lambda p:p.name,key='official_snapshot_choice')
    try:
        manifest = chosen/'manifest.json'
        season = json.loads(manifest.read_text()).get('run_metadata',{}).get('season','2026-2027') if manifest.exists() else '2026-2027'
        history=quick_refresh.select_history_snapshot(paths,chosen,season=season)
        if history is None:
            st.error('Ingen tidligere komplet spillerhistorik før dette snapshot. Hent fuld spillerhistorik først.');return
        history_manifest=history/'manifest.json'
        data = _load_data(str(chosen),manifest.stat().st_mtime_ns if manifest.exists() else 0,
                          str(history),history_manifest.stat().st_mtime_ns if history_manifest.exists() else 0,season)
    except (OSError,ValueError,KeyError) as exc:
        st.error(str(exc));return
    now = datetime.now(timezone.utc)
    age = (now-utc(data['as_of_at'])).total_seconds()/3600
    history_at=data.get('input_sources',{}).get('history',{}).get('available_at',data['as_of_at'])
    history_gap=data.get('coverage',{}).get('history_refresh_required',False)
    st.caption(f"Priser, status, kampe og deadlines: {utc(data['as_of_at']).strftime('%d/%m kl. %H:%M UTC')} · {age:.1f} timer gamle")
    st.caption(f"Kampvis historik: {utc(history_at).strftime('%d/%m kl. %H:%M UTC')} · snapshot {history.name}")
    st.caption('Hurtig opdatering henter priser, status og kampplan; kampvis historik beholder sit oprindelige hentetidspunkt.')
    if st.button('Hent seneste data'):
        try:
            with st.spinner('Henter officiel kontekst og gemmer nyt snapshot…'):
                fresh=quick_refresh.capture_official_context(LOCAL_ROOT/'data/raw',season=season)
            st.session_state['pending_official_snapshot_choice']=fresh
            st.rerun()
        except (FPLSourceError,SnapshotError,OSError,ValueError) as exc:
            st.error(f'Opdatering mislykkedes ({type(exc).__name__}); det valgte datagrundlag er uændret.')
    if history_gap:
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
    if age>24:
        st.warning('Datagrundlaget er over et døgn gammelt. Kontrollér især priser, skader og kampplan før en transfer.')
    if history_gap:
        coverage=data['coverage']
        st.warning('Kampvis historik mangler nyligt afsluttede kampe, begyndte kampe eller nye spillere i dette kontekstsnapshot. '
                   f"Begyndte kamp-ID’er: {coverage.get('newly_started_fixture_ids',[])} · "
                   f"afsluttede kamp-ID’er: {coverage.get('newly_finished_fixture_ids',[])} · "
                   f"nye spiller-ID’er: {coverage.get('new_player_ids_without_history',[])}. "
                   'Hent fuld spillerhistorik, før du beregner nye transferforslag.')
    pool = {p['id']:p for p in data['players']}
    clubs = {t['id']:t.get('short_name',t.get('name',str(t['id']))) for t in data['teams']}
    labels = {i:f"{p['web_name']} · {clubs[p['team']]} · #{i}" for i,p in pool.items()}
    season = data.get('season','2026-2027')
    profile_path = LOCAL_ROOT/'data/processed/my_team.json'
    if 'team_draft' not in st.session_state:
        try:
            _reset_editor(load_profile(profile_path) if profile_path.exists() else {})
        except (OSError,ValueError,KeyError) as exc:
            st.error(f'Gemt hold kunne ikke åbnes: {exc}');_reset_editor({})
    overview = st.container()
    with st.expander('Redigér hold · import, spillere og økonomi', expanded=not bool(st.session_state['team_draft'].get('players'))):
        render_import(data,LOCAL_ROOT,_reset_editor)
        c1,c2,c3 = st.columns(3)
        if c1.button('Genindlæs gemt hold',disabled=not profile_path.exists()):
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
        st.subheader('Dine 15 spillere og faktiske salgsværdier')
        st.caption('Salgsværdier er dem, FPL viser når du sælger. Købspriser bruges ikke som automatisk erstatning.')
        selected=[]; slot=0
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
        cols=st.columns(3)
        st.session_state.setdefault('owned_bank',draft['bank']/10 if draft.get('bank') is not None else None)
        st.session_state.setdefault('owned_free',draft.get('free_transfers',1))
        st.session_state.setdefault('owned_made',draft.get('transfers_made',0))
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
        try:
            if free is None or made is None:raise ValueError('Angiv resterende gratis transfers og antal transfers allerede foretaget denne GW.')
            profile=dict(schema_version=1,season=draft.get('season',season),players=[dict(player_id=i,selling_price=money(s)) for i,s in selected],
                         bank=money(bank),free_transfers=int(free),transfers_made=int(made),**chip_fields)
            validate_profile(profile,data['players'],season=season)
            if draft.get('import_provenance'):profile['import_provenance']=draft['import_provenance']
        except (ValueError,TypeError,KeyError) as exc:error=str(exc)
        if st.button('Gem hold'):
            if error:st.error(error)
            else:
                save_profile(profile,profile_path);st.session_state['team_draft']=profile
                st.success('Holdet er gemt lokalt. Forslag ændrer ikke dit hold automatisk.')
    with overview:
        future_events=[e for e in data['events'] if utc(e['deadline_time'])>now]
        next_event=min(future_events,key=lambda e:e['id']) if future_events else None
        ids=list(dict.fromkeys(i for i,_ in selected if i in pool))
        summary_metrics([
            ('Næste deadline',f"GW{next_event['id']}" if next_event else 'Ukendt',
             utc(next_event['deadline_time']).strftime('%d/%m · %H:%M UTC') if next_event else 'Opdatér kampkontekst'),
            ('Bank',f'£{bank:.1f}m' if bank is not None else 'Udfyld','Dit transferbudget'),
            ('Gratis transfers',str(free) if free is not None else 'Udfyld','Til rådighed nu'),
            ('Din trup',f'{len(ids)} / 15','Spillere valgt')])
        st.subheader('Dit holdoverblik')
        st.caption('Truppen vist efter position. Anbefalet XI, bænk og anfører vises i transferforslagene efter beregning.')
        if ids:
            cards=[]
            for i in ids:
                p=pool[i];chance=p.get('chance_of_playing_next_round')
                flag=('Tvivl' if p.get('status')=='d' else 'Status '+str(p['status'])) if p.get('status') not in (None,'a') else ''
                if flag and chance is not None:flag+=f' · {chance}%'
                cards.append(dict(id=i,name=p['web_name'],position=p['element_type'],
                    detail=f"{clubs[p['team']]} · køb £{p['now_cost']/10:.1f}m",flag=flag))
            st.html(pitch_html(cards))
            st.caption('Statusmærker er FPL’s aktuelle vurdering i det valgte snapshot, ikke modellens startchance.')
        else:
            st.info('Start med dit hold-ID eller vælg dine spillere under Redigér hold nedenfor.')
        if error:st.caption('Holdet mangler gyldige oplysninger. Åbn Redigér hold før du beregner forslag.')
    st.subheader('Din næste beslutning')
    future=[e['id'] for e in data['events'] if utc(e['deadline_time'])>now]
    if not future:
        st.error('Snapshot har ingen fremtidige deadlines. Opdatér datagrundlaget.');return
    start=min(future)
    with st.expander('Planlæg transfers · horisont og indstillinger', expanded=False):
        st.write(f'Første GW: **{start}** · transfers foretages nu før næste deadline.')
        available=1
        while available<4 and start+available in future:
            available+=1
        horizon=st.selectbox('Horisont (GWs)',list(range(1,available+1)))
        events=list(range(start,start+horizon))
        chip_plan=render_chip_schedule(profile,events,data,now.isoformat()) if profile and not error else {}
        mode=st.selectbox('Planlægning',['Transfers uge for uge','Alle transfers nu'])
        sequential=mode=='Transfers uge for uge'
        cols=st.columns(2)
        maximum=cols[0].number_input('Maksimalt antal transfers pr. GW' if sequential else 'Maksimalt antal nye transfers',min_value=0,max_value=15,value=2 if sequential else 1,step=1)
        hits=cols[1].checkbox('Tillad pointfradrag (−4 pr. ekstra transfer)',value=False)
        owned=[i for i,_ in selected if i in pool]
        locked=st.multiselect('Behold disse spillere',sorted(set(owned)),format_func=labels.get)
        excluded=st.multiselect('Udeluk fra forslag',sorted(pool,key=labels.get),format_func=labels.get)
        st.caption('Behold/udeluk gælder alle valgte GWs. Udelukker du en ejet spiller, skal forslagene sælge ham nu; behold-referencen ændres ikke.')
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
        with st.expander('Beregningsindstillinger og antagelser'):
            draws=st.selectbox('Scenarier',[3000,1000,500,10000])
            seed=st.number_input('Seed',min_value=0,max_value=2147483647,value=42,step=1)
            st.write('Standardmodellen og priserne bevares. Tilgængelighed følger det valgte scenarie; manuelle GW-antagelser har forrang. '
                     'Chips placeres manuelt. Bænkvægt i kandidatsøgningen: 0,1; Bench Boost værdisætter hele truppen.')
    request=(str(chosen),data.get('manifest_sha256'),tuple(events),model,str(odds_path),str(set_piece_config),str(set_piece_path),str(bonus_config),str(season_prior_config),str(assist_config),draws,int(seed),availability_policy,json.dumps([assumptions,sensitivity,roles],sort_keys=True))
    signature=(request,json.dumps(profile,sort_keys=True),mode,maximum,total,hits,tuple(sorted(locked)),tuple(sorted(excluded)),json.dumps(chip_plan,sort_keys=True))
    st.caption(f"GW{events[0]}–{events[-1]} · {mode} · højst {int(maximum)} transfers {'pr. GW' if sequential else 'nu'} · {'hits tilladt' if hits else 'uden hits'} · {model}")
    if st.button('Sammenlign transferforslag',type='primary',disabled=history_gap):
        if error:st.error(error)
        else:
            try:
                if chip_plan and not sequential:raise ValueError('Chips kræver Planlægning: Transfers uge for uge.')
                from fpl_model.chips import validate_chip_plan
                validate_chip_plan(chip_plan,profile,events,deadlines={e['id']:e['deadline_time'] for e in data['events']},origin_at=now.isoformat())
                if st.session_state.get(state_prefix+'forecast_request')!=request:
                    st.session_state[state_prefix+'forecast_request']=request
                    st.session_state[state_prefix+'forecast_origin']=now.isoformat()
                origin=st.session_state[state_prefix+'forecast_origin']
                odds=None
                if uses_odds:
                    odds=load_odds(odds_path,'the_odds_api') if odds_path else ([],dict(source='the_odds_api',
                        available_at=origin,retrieved_at=origin,failure='no_saved_odds'))
                set_piece_source=None
                if set_piece_config is not None:
                    from fpl_model.set_piece_roles import load_roles
                    set_piece_source=load_roles(set_piece_path)
                status=st.empty()
                bundle=forecast_bundle(data,events,BaselineConfig(),origin_at=origin,
                    cache_root=LOCAL_ROOT/'artifacts/transfer_forecasts',draws=draws,seed=int(seed),odds=odds,progress=status.info,
                    availability=scenario_records(assumptions,sensitivity,events,origin,'a'),availability_policy=availability_policy,odds_scope=odds_scope,evolution=evolution,
                    role_assumptions=[dict(r,observed_at=origin) for r in roles],set_piece_config=set_piece_config,set_piece_source=set_piece_source,bonus_config=bonus_config,season_prior_config=season_prior_config,assist_config=assist_config)
                if sequential:
                    report=compare_sequences(bundle,profile,max_per_gw=int(maximum),max_total=int(total),
                                             locked=locked,excluded=excluded,allow_hits=hits,progress=status.info,chip_plan=chip_plan)
                    if sensitivity:
                        report['scenario_label']=f"A · {sensitivity['name']} tilgængelig fra GW{sensitivity['return_a']}"
                        alternative=forecast_bundle(data,events,BaselineConfig(),origin_at=origin,
                            cache_root=LOCAL_ROOT/'artifacts/transfer_forecasts',draws=draws,seed=int(seed),odds=odds,
                            progress=status.info,availability=scenario_records(assumptions,sensitivity,events,origin,'b'),availability_policy=availability_policy,odds_scope=odds_scope,evolution=evolution,
                    role_assumptions=[dict(r,observed_at=origin) for r in roles],set_piece_config=set_piece_config,set_piece_source=set_piece_source,bonus_config=bonus_config,season_prior_config=season_prior_config,assist_config=assist_config)
                        report['sensitivity']=compare_sensitivity(report,alternative,progress=status.info,
                            label=f"A: tilgængelig fra GW{sensitivity['return_a']} · B: fra GW{sensitivity['return_b']} · {sensitivity['name']}")
                else:
                    report=compare_packages(bundle,profile,max_transfers=int(maximum),locked=locked,excluded=excluded,
                                            allow_hits=hits,progress=status.info)
                output=save_report(report,LOCAL_ROOT/'artifacts/transfers')
                st.session_state.update({state_prefix+'transfer_result':report,state_prefix+'transfer_signature':signature,state_prefix+'transfer_output':str(output)})
                status.success('Sammenligningen er gemt. Dit hold er ikke ændret.')
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
    with st.expander('Åbn tidligere transferforslag'):
        saved=sorted((LOCAL_ROOT/'artifacts/transfers').glob('*/report.json'),reverse=True)
        if saved:
            path=st.selectbox('Gemt sammenligning',saved,format_func=lambda p:p.parent.name)
            if st.button('Åbn gemt sammenligning'):
                try:
                    st.session_state.update({state_prefix+'transfer_result':json.loads(path.read_text()),state_prefix+'transfer_signature':None,state_prefix+'transfer_output':str(path.parent)})
                except (ValueError,OSError) as exc:st.error(str(exc))
        else:st.caption('Ingen gemte transferforslag endnu.')
    if state_prefix+'transfer_result' in st.session_state:
        if st.session_state.get(state_prefix+'transfer_signature')!=signature:
            st.warning('Viser en gemt beregning med dens oprindelige hold og indstillinger. Kør igen for dine aktuelle valg.')
        st.caption(f"Rapport: {st.session_state.get(state_prefix+'transfer_output')}")
        show_report(st.session_state[state_prefix+'transfer_result'])
