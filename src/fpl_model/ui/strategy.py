"""News context, explicit availability scenarios and sequence report presentation."""
import json
import pandas as pd
import streamlit as st
from fpl_model.chips import LABELS
from fpl_model.ui.presentation import show_lineup_pitch, transfer_card, summary_metrics


def availability_controls(data,owned,events,labels,*,allow_sensitivity=True):
    pool={p['id']:p for p in data['players']};records=[];sensitivity=None
    with st.expander('Skader, FPL-nyheder og GW-antagelser'):
        st.caption(f"Officielt snapshot: {data['snapshot_id']} · hentet/available_at {data['as_of_at']}. Ingen automatisk nyhedshentning.")
        st.dataframe(pd.DataFrame([dict(Spiller=labels[i],Status=pool[i].get('status'),
            **{'FPL spillechance næste GW':pool[i].get('chance_of_playing_next_round'),
               'Nyhed':pool[i].get('news') or 'Ingen nyhedstekst',
               'FPL news_added':pool[i].get('news_added')}) for i in sorted(set(owned))]),hide_index=True)
        st.caption('FPL-spillechance er ikke en kalibreret startchance. Skade, karantæne og rotation er forskellige forhold. '
                   'En rask spiller kan stadig være reserve. news_added vises som et kildefelt, ikke som bevis for historisk tilgængelighed.')
        st.write('Tilgængelighed i senere GWs følger det valgte planlægningsscenarie. Manuelle faktorer har forrang. '
                 'Ingen returdato udledes automatisk af nyhedsteksten.')
        selected=st.multiselect('Spillere med manuelle GW-antagelser',sorted(pool,key=labels.get),format_func=labels.get)
        for pid in selected:
            st.write(f"**{labels[pid]}** · {pool[pid].get('news') or 'Ingen FPL-nyhed'}")
            reason=st.text_input(f'Begrundelse · {labels[pid]}',key=f'injury_reason_{pid}')
            source=st.text_input(f'Kildelink (valgfrit) · {labels[pid]}',key=f'injury_link_{pid}')
            cols=st.columns(len(events))
            for col,event in zip(cols,events):
                factor=col.number_input(f'Faktor · {labels[pid]} · GW{event}',min_value=0.,max_value=1.,
                                        value=None,step=.05,key=f'injury_{pid}_{event}')
                if factor is not None:
                    records.append(dict(player_id=pid,event=event,factor=float(factor),reason=reason,source_url=source or None))
        st.caption('Tomt felt = valgt politik for tilgængelighed. 0 = ude; 1 = ingen yderligere skadesreduktion. '
                   'Faktoren erstatter den eksisterende faktor; historiske start-/indhoprater og betingede minutter bevares. '
                   'Det er en planlægningsantagelse, ikke en medicinsk sandsynlighed.')
        if allow_sensitivity and st.checkbox('Sammenlign to mulige returtidspunkter',disabled=len(events)<2):
            suspects=[i for i in set(owned) if pool[i].get('status') not in (None,'a')]
            options=sorted(pool,key=lambda i:(i not in suspects,i not in owned,labels[i]))
            pid=st.selectbox('Spiller til følsomhed',options,format_func=labels.get)
            returns=events+[events[-1]+1]
            label=lambda e:f'GW{e}' if e in events else 'Efter horisonten'
            a=st.selectbox('Scenarie A: tilgængelig fra',returns,index=min(1,len(events)-1),format_func=label)
            b=st.selectbox('Scenarie B: tilgængelig fra',returns,index=min(2,len(returns)-1),format_func=label)
            st.warning('Hypotetisk følsomhed: spilleren får faktor 0 før den valgte GW og 1 fra den. '
                       'Begge scenarier erstatter spillerens andre GW-antagelser. Dette er ikke en faktisk raskmelding.')
            sensitivity=dict(player_id=pid,return_a=a,return_b=b,name=labels[pid])
    return records,sensitivity


def scenario_records(records,sensitivity,events,origin,which):
    out=[dict(r,observed_at=origin) for r in records]
    if sensitivity:
        pid=sensitivity['player_id'];ret=sensitivity[f'return_{which}']
        out=[r for r in out if r['player_id']!=pid]
        out += [dict(player_id=pid,event=e,factor=float(e>=ret),observed_at=origin,
                     reason=f'Hypotetisk scenarie {which.upper()}: tilgængelig fra GW{ret}',source_url=None) for e in events]
    return out


def show_sequence_report(report):
    f=report['forecast'];pool={p['player_id']:p for p in next(iter(report['players_by_event'].values()))}
    names=lambda ids:', '.join(pool[i]['name'] for i in ids) or '—'
    st.subheader('Strategi uge for uge')
    st.caption(f"Prognose fra {f['forecast_origin_at']} · data fra {f['source_available_at']} · {f['model_version']} · {f['draws']} scenarier · seed {f['seed']}")
    if f.get('availability_policy')=='short_doubt_next_gw':
        st.warning('Denne rapport antager, at 75%-tvivl ophører efter første GW. Det er et planlægningsscenarie, ikke en verificeret raskmelding.')
    if report.get('scenario_label'):st.warning('Hypotetisk hovedscenarie: '+report['scenario_label'])
    st.info('0 transfers nu kan følges af transfers senere. Behold-alternativet foretager ingen transfers i hele horisonten. '
            'Planen bruger dagens information; genberegn den efter nye nyheder.')
    refined=bool(report['packages'][0].get('lineup_policy'))
    st.caption('Målværdien er holdpoint inkl. autosubs og vice i planlægningsscenarier. XI, bænkerækkefølge og anfører/vice '
               'er udtømmende optimeret for hver kandidattrup. Simulerede point bruger separate evalueringsscenarier. '
               'Solver/gap gælder kun den tilnærmede søgning efter transfertrupper — ikke et globalt autosub-optimum.' if refined else
               'Ældre rapport: XI er valgt med vægtet bænk; autosubs indgår kun i efterfølgende evaluering.')
    rows=[]
    for p in report['packages']:
        rows.append(dict(Strategi=p['label'],**{'Transfers pr. GW':' → '.join(str(s['count']) for s in p['steps']),
            'Ud nu':names(p['steps'][0]['out']),'Ind nu':names(p['steps'][0]['in']),
            'Bank nu £m':p['steps'][0]['bank_after']/10,'Hits i alt':p['hits'],
            'Hypotetisk reference':p.get('hypothetical',False),'Forskel til bedste uden chips':round(p.get('gain_vs_best_no_chip',0),3),'Gevinst næste GW':round(p['next_gw_gain'],3),'Gevinst horisont':round(p['total_gain'],3),
            'Simulerede point, netto':round(p['total_points'],3),'Målværdi, netto':round(p['objective'],3),
            'Kandidatsøgning':p['solver']['status'],'Kandidat-gap %':round(100*p['solver']['gap'],3)}))
    with st.expander('Sammenlign alle strategier · point, transfers og solver'):
        st.dataframe(pd.DataFrame(rows),hide_index=True)
    best=next((p for p in report['packages'] if p['plan_id']==report['recommendation']['plan_id']),None)
    if best:
        st.write(f"Bedste fundne plan efter optimizerens målværdi: **{best['label']}**.")
        st.caption('Bedst inden for de valgte begrænsninger. Små prognoseforskelle kan være simulationsstøj; restværdien af gratis transfers efter horisonten er ikke prissat.')
    for fail in report['unavailable_packages']:st.caption(f"{fail['first_count']} transfers nu: {fail['reason']}")
    report_id=(report.get('created_at'),f.get('cache_key'),tuple(p['plan_id'] for p in report['packages']))
    if st.session_state.get('sequence_detail_report')!=report_id:
        st.session_state['sequence_detail_report']=report_id
        st.session_state['sequence_detail']=next((i for i,p in enumerate(report['packages']) if p is best),0)
    ix=st.selectbox('Strategi – se ugeplan',range(len(rows)),format_func=lambda i:rows[i]['Strategi'],key='sequence_detail')
    plan=report['packages'][ix]
    summary_metrics([
        ('Simulerede point',f"{plan['total_points']:.2f}",'Hele horisonten · netto'),
        ('Gevinst mod behold',f"{plan['total_gain']:+.2f}",'Samme prognoser · netto'),
        ('Optimizerens målværdi',f"{plan['objective']:.2f}",'Planlægningsscenarier · netto')])
    if plan.get('hypothetical'):st.warning('Hypotetisk reference: en chip er allerede aktiv på FPL; denne plan uden chip kan ikke vælges.')
    if report['config'].get('chip_plan'):
        st.caption('Chipforskelle er prognoser på den valgte korte horisont, ikke en automatisk optimal chipkalender frem til GW19.')
    step=plan['steps'][0]
    transfer_card(plan['label'],names(step['out']),names(step['in']),step['bank_after'],plan['hits'],plan['total_gain'])
    st.dataframe(pd.DataFrame([dict(GW=s['event'],Ud=names(s['out']),Ind=names(s['in']),**{
        'Chip':LABELS.get(s.get('chip'),'Ingen'),'Transfers':s['count'],'Almindelige':s.get('ordinary_count',s['count']),'Omlægning':s.get('relocation_count',0),'Bank £m':s['bank_after']/10,'Permanent bank £m':s.get('permanent_bank_after',s['bank_after'])/10,'Salg £m':s['sale_proceeds']/10,
        'Køb £m':s['purchase_cost']/10,'FT før':s['available'],'Gratis brugt':s['used'],
        'FT tilbage':s['remaining'],'FT næste GW':s['next_gw'],'Hits':s['hits'],'Heraf eksisterende hits':s.get('existing_hits',0)}) for s in plan['steps']]),hide_index=True)
    display_rows=[dict(r,chip=LABELS.get(r.get('chip'),'Ingen'),bench_contribution_kind='Bench Boost' if r.get('chip')=='bench_boost' else 'Autosubs') for r in plan['per_gw']]
    st.dataframe(pd.DataFrame(display_rows).round(2).rename(columns={'chip':'Chip','bench_contribution_kind':'Bænkregel','hits':'Pointfradrag','event':'GW','mean':'Simulerede point, netto',
        'gain':'Gevinst mod behold','objective':'Målværdi, netto','bench_mean':'Bænkbidrag (autosubs / BB)',
        'previous_lineup_mean':'Tidligere opstillingsmetode','lineup_gain':'Gevinst fra nyt opstillingsvalg'}),hide_index=True)
    for step in plan['steps']:
        if step.get('chip')=='free_hit':
            st.info(f"Free Hit GW{step['event']}: dette hold er midlertidigt. Permanent trup efter runden: {names(step['permanent_squad_after'])}. Bank: £{step['permanent_bank_after']/10:.1f}m.")
    _show_lineups(report,plan)
    with st.expander('Hvorfor spiller/bænker modellen min spiller?'):
        owned={p['player_id'] for p in report['profile']['players']}
        pid=st.selectbox('Spiller – spilletid pr. GW',sorted(owned),format_func=lambda i:pool[i]['name'])
        table=[]
        for event,players in report['players_by_event'].items():
            r=next(r for r in players if r['player_id']==pid)
            table.append(dict(GW=event,Spiller=r['name'],Historikkampe=r['history_rows'],
                Faktor=r.get('availability_factor'),Startchance=r.get('p_start'),
                Start_givet_tilgængelig=r.get('p_start_given_available'),Rollemodel=r.get('role_model'),Returbegrænsning=r.get('return_assumption'),
                Minutter=round(r['expected_minutes'],1),xP=round(r['xp'],2),
                Antagelse=r.get('availability_assumption','Ikke gemt i ældre rapport')))
        st.dataframe(pd.DataFrame(table),hide_index=True)
        st.caption('Faktor 1 fjerner kun den ekstra skadesreduktion. Historik, rotation, modstandere og alternativer i truppen '
                   'kan stadig føre til en bænkplads. Startchance gælder pr. kamp; minutter og xP summeres over GWens kampe.')
    if 'sensitivity' in report:
        s=report['sensitivity'];st.subheader('Følsomhed over for returtidspunkt')
        st.warning('Hypotetisk sammenligning — ikke nye nyheder eller dokumentation for bedre modelperformance.')
        st.write(s['label'])
        st.write('Anbefalede transfers nu ændres: '+('ja' if s['changed_first_transfers'] else 'nej' if s['changed_first_transfers'] is False else 'kan ikke vurderes'))
        st.caption('Tabellen fastholder hver A-plan og vurderer den i B. Gevinst måles mod behold-holdet i det samme scenarie.')
        st.dataframe(pd.DataFrame(s['fixed_plans']).rename(columns={'label':'Fast plan','base_points':'Point A',
            'alternative_points':'Point B','gain_in_base':'Gevinst A','gain_in_alternative':'Gevinst B','change_in_gain':'Ændret gevinst'}),hide_index=True)
        with st.expander('Genoptimerede planer i scenarie B'):
            # Distinct widget key; avoid recursive sensitivity reports.
            alternative=s['alternative'];selected=st.selectbox('Scenarie B – strategi',range(len(alternative['packages'])),
                format_func=lambda i:alternative['packages'][i]['label'],key='sensitivity_plan')
            p=alternative['packages'][selected]
            st.write(f"Simulerede nettopoint: {p['total_points']:.2f} · gevinst mod B-behold: {p['total_gain']:.2f} · solver {p['solver']['status']} · gap {100*p['solver']['gap']:.3f}%")
            st.dataframe(pd.DataFrame([dict(GW=x['event'],Ud=names(x['out']),Ind=names(x['in']),
                Bank=x['bank_after']/10,Hits=x['hits'],Anfører=names([p['lineups'].get(x['event'],p['lineups'].get(str(x['event'])))['captain']])) for x in p['steps']]),hide_index=True)
            _show_lineups(alternative,p,prefix='Scenarie B · ')
    with st.expander('Datagrundlag, odds og antagelser'):
        if report['forecast'].get('set_piece_config'):
            st.warning('Gemte dødboldsantagelser – følsomhedsscenarie, ikke kalibrerede frekvenser.')
            st.json(dict(config=report['forecast']['set_piece_config'],source=report['forecast'].get('set_piece_source')))
        from fpl_model.ui.bonus import bonus_notice
        bonus_notice(report['forecast'].get('bonus_config'),report['forecast'].get('bonus_training'))
        if f.get('assist_config'):
            st.caption('Eksperiment: FPL-assistkorrektion. Kun assistdelen ændres.')
            st.json(f.get('assist_training',{}))
        if f.get('season_prior_config'):
            st.caption('Eksperiment: sidste sæsons xG/xA-prior. Spilletid/bonus uændret; manglende historik bruger positionsprior.')
            st.json(f['season_prior_config'])
        st.write(f"Officielt snapshot: {f['snapshot_id']}")
        st.write('Manuelle antagelser:',f.get('availability_assumptions',[]))
        st.write('Scenarieantagelser:',f.get('derived_availability_assumptions',[]))
        for event,c in report['odds_coverage'].items():
            if c is None:st.write(f'GW{event}: baseline uden odds.')
            else:
                st.write(f"GW{event}: {c['usable']}/{c['expected_fixtures']} med odds · {c['bookmaker']}")
                st.caption(f"Odds observeret: {c['source'].get('available_at','ukendt')}. Publikationstid ikke udledt.")
                st.dataframe(pd.DataFrame(c['fixtures']),hide_index=True)
        if f['unassigned_fixture_ids'] or f['undated_fixture_ids']:
            st.warning('Uafklarede GWs/kamptider findes; kampe er ikke placeret ved gæt.')
            st.write(dict(uden_GW=f['unassigned_fixture_ids'],uden_tid=f['undated_fixture_ids']))
        for note in report['limitations']:st.caption(note)
    st.download_button('Download strategi (JSON)',json.dumps(report,ensure_ascii=False,indent=2),file_name='transferstrategi.json',mime='application/json')


def _show_lineups(report,plan,prefix=""):
    tabs=st.tabs([f'{prefix}GW{e}' for e in plan['lineups']])
    for tab,(event,lineup) in zip(tabs,plan['lineups'].items()):
        lookup={r['player_id']:r for r in (report['players_by_event'].get(event) or report['players_by_event'][str(event)])}
        with tab, st.expander(f'{prefix}GW{event} · XI, bænk og anfører',expanded=True):
            if lineup.get('chip'):st.write('**'+LABELS[lineup['chip']]+'**')
            if 'planning_bench_points' in lineup:
                contribution='Bench Boost-bidrag' if lineup.get('chip')=='bench_boost' else 'autosub-point'
                st.caption(f"Forventede {contribution} i planlægningsscenarier: {lineup['planning_bench_points']:.2f}. "
                           f"Holdpoint inkl. anfører/vice: {lineup['objective']:.2f}; tidligere XI på samme scenarier: {lineup['previous_planning_points']:.2f}. "
                           'Opstillingen fastlægges før kampene — ingen valg med kendskab til udfaldet.')
            show_lineup_pitch(lookup,lineup)
            table=[]
            for pid in lineup['starters']+lineup['bench']:
                r=lookup[pid]
                role='XI' if pid in lineup['starters'] else ('Bænk GK' if r['position']==1 else f"Bænk {lineup['bench'].index(pid)}")
                if pid==lineup['captain']:role+=' · anfører'
                elif pid==lineup['vice_captain']:role+=' · vice'
                table.append(dict(Spiller=r['name'],Rolle=role,**{'Pris £m':r['price']/10,'xP':round(r['xp'],3),
                    'Forv. minutter':round(r['expected_minutes'],1),'Kampe':len(r['fixture_ids']),'Fallback':r['fallbacks']}))
            st.dataframe(pd.DataFrame(table),hide_index=True)
