"""Local Streamlit front end. Forecasts, scenarios and optimization live in src/."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import BaselineConfig
from fpl_model.prototype_data import load_data, snapshot_paths
from fpl_model.prototype import run_prototype, save_run
from fpl_model.backtest.walk_forward import EVALUATION_VERSION
from fpl_model.diagnostics import DIAGNOSTICS_VERSION
from fpl_model.minutes_experiment import comparison_paths, summarize_seeds, EXPERIMENT_VERSION
from fpl_model.odds_comparison import comparison_paths as odds_comparison_paths

st.set_page_config(page_title='FPL Lab',page_icon='⚽',layout='wide')
st.title('FPL Lab · én gameweek')
st.caption('Reelle FPL-data → foreløbig prognose → simulation → holdforslag')
st.warning('Eksperimentel baseline. Fordelingerne er ikke dokumenteret kalibrerede. Ingen transfers, salgsværdier eller chips.')
paths=snapshot_paths(ROOT/'data/raw')
if not paths:
    st.error('Ingen verificeret FPL-snapshot. Kør den eksisterende snapshot-CLI først.');st.stop()
chosen=st.sidebar.selectbox('Datagrundlag',paths,format_func=lambda p:p.name)
try:
    data=load_data(chosen)
except (ValueError,KeyError,OSError) as exc:
    st.error(f'Snapshot kan ikke læses: {exc}');st.stop()
clubs={t['id']:t['short_name'] for t in data['teams']}
labels={p['id']:f"{p['web_name']} · {clubs[p['team']]} · #{p['id']}" for p in data['players']}
age=(datetime.now(timezone.utc)-utc(data['as_of_at'])).total_seconds()/86400
st.info(f"Data observeret {data['as_of_at']} · {max(age,0):.1f} dage gamle · {len(data['players'])} spillere · "
        f"{len({r['player_id'] for r in data['histories']})} med kampvis historik. Ingen nye downloads ved appstart.")
coverage=data.get('coverage')
if coverage:
    st.write(f"**Dækning:** {coverage['attempted_players']} forsøgt · {coverage['successful_responses']} gyldige svar · "
             f"{len(coverage['empty_history_players'])} tomme historikker · {len(coverage['failed_players'])} fejl · "
             f"{len(coverage['missing_response_players'])} uden gyldigt svar · {coverage['accepted_rows']} brugbare spiller-kampe.")
    st.caption(f"{coverage['explicit_zero_minute_rows']} eksplicitte nulminuttersrækker · {coverage['quarantined_rows']} i karantæne. "
               'Tom historik eller manglende svar er ikke DNP. Huller/uklar klubhistorik bruges ikke som deltagelsesnævner.')
    with st.expander('Dækning pr. spiller og ny dataindsamling'):
        st.dataframe(pd.DataFrame(coverage['players']),hide_index=True)
        st.write('Hent et nyt snapshot eksplicit i terminalen, og genindlæs derefter appen:')
        st.code('.venv/bin/python scripts/capture_all_players.py --season 2026-2027 --request-interval 0.5',language='bash')
events=[e['id'] for e in data['events'] if utc(e['deadline_time'])>utc(data['as_of_at'])]
if not events: st.error('Snapshot har ingen fremtidige deadlines.');st.stop()
event=st.sidebar.selectbox('Gameweek (én ad gangen)',events)
deadline=next(e['deadline_time'] for e in data['events'] if e['id']==event)
st.sidebar.caption(f'Officiel deadline i snapshot: {deadline}')
budget=st.sidebar.number_input('Budget (£m, ny trup)',min_value=60.,max_value=150.,value=100.,step=.1)
draws=st.sidebar.select_slider('Scenarier',options=[500,1000,3000,10000],value=3000)
seed=st.sidebar.number_input('Random seed',min_value=0,max_value=2147483647,value=42,step=1)
with st.sidebar.expander('Centrale modelantagelser'):
    prior=st.number_input('Rate-prior: kampe',min_value=.1,max_value=30.,value=3.,step=.5)
    minute_prior=st.number_input('Betingede minutter: priorstyrke',min_value=.1,max_value=20.,value=1.,step=.5)
    start_minutes=st.slider('Minutter ved start (prior)',45,90,82)
    attack=st.slider('Angrebsrate ×',.3,2.,1.,.05)
    home=st.slider('Hjemmeholdets mål-prior',.5,3.,1.55,.05)
    away=st.slider('Udeholdets mål-prior',.5,3.,1.25,.05)
    injury=st.slider('Ukendt skadeschance: tilgængelighed',0.,1.,.25,.05)
    bench_weight=st.slider('Bænkvægt i optimizer (tilnærmelse)',0.,.5,.1,.05)
locked=st.sidebar.multiselect('Lås i trup',list(labels),format_func=labels.get)
excluded=st.sidebar.multiselect('Udeluk',list(labels),format_func=labels.get)
config=BaselineConfig(prior_games=prior,minutes_prior_games=minute_prior,starter_minutes=start_minutes,
                      attack_scale=attack,home_goals=home,away_goals=away,injury_unknown_factor=injury)
signature=(EXPERIMENT_VERSION,DIAGNOSTICS_VERSION,EVALUATION_VERSION,str(chosen),event,budget,draws,int(seed),config,tuple(locked),tuple(excluded),bench_weight)
if st.button('Kør prognose, simulation og optimering',type='primary'):
    try:
        with st.spinner('Simulerer spillere, vælger lovligt hold og evaluerer i nye scenarier …'):
            result=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,
                                  locked=locked,excluded=excluded,bench_weight=bench_weight)
        st.session_state['result']=result;st.session_state['signature']=signature
        st.session_state['saved_run']=str(save_run(result[0]))
    except (ValueError,RuntimeError,OSError) as exc:
        st.error(str(exc))
        st.session_state.pop('result',None)
# Loading a saved comparison never runs an experiment or downloads data.
@st.cache_data(show_spinner=False)
def read_comparison(path):
    return json.loads(Path(path).read_text())

with st.expander('Tre frekvenspriorer · gemt udviklingseksperiment',expanded=True):
    st.warning('GW3–5 er udviklingsdata, allerede brugt til diagnostik. Ingen uafhængig testperformance '
               'eller statistisk sikker forbedring. Standardmodellen er ikke ændret.')
    comparisons=[]
    for path in comparison_paths(ROOT/'artifacts/minutes_experiments'):
        try:
            candidate=read_comparison(str(path))
            if candidate['snapshot_id']==data['snapshot_id'] and candidate.get('manifest_sha256')==data.get('manifest_sha256'):
                comparisons.append(path)
        except (OSError,ValueError,KeyError):
            st.warning(f'Kunne ikke læse gemt sammenligning: {path.name}')
    if comparisons:
        comparison_path=st.selectbox('Gemt prior-eksperiment',comparisons,format_func=lambda p:p.parent.name)
        comparison=read_comparison(str(comparison_path))
        st.caption(f"{comparison['n']} spiller-GW-rækker · GW {comparison['gameweeks']} · "
                   f"{comparison['draws']} scenarier pr. GW · seeds {comparison['seeds']}. "
                   'Frekvenspriorer: 1,0 / 0,25 / 0,10; betingede minutter: 1,0 for alle. '
                   'Sidebarens prognoseindstillinger ændrer ikke dette gemte eksperiment.')
        metrics=pd.DataFrame(comparison['metrics'])
        summary=pd.DataFrame(comparison.get('seed_summary') or summarize_seeds(comparison['metrics']))
        labels_experiment={'component_baseline_v1':'Baseline 1,0','component_frequency_025_v1':'Prior 0,25',
                           'component_frequency_010_v1':'Prior 0,10','historical_mean_reference':'Simpel reference'}
        metric_names={'minutes_bias':'Minut-bias','minutes_mae':'Minut-MAE','minutes_rmse':'Minut-RMSE',
            'point_mae':'Point-MAE','point_rmse':'Point-RMSE','dnp_brier':'DNP-Brier','point_crps':'CRPS',
            'dnp_predicted':'DNP forudsagt','dnp_observed':'DNP observeret'}
        def compact_table(rows):
            view=[]
            rows=rows.assign(_order=rows.model_version.map({name:i for i,name in enumerate(labels_experiment)})).sort_values(['group','_order'])
            for _,row in rows.iterrows():
                entry={'Variant':labels_experiment[row.model_version],'Gruppe':row.group,'n':row.n,'Spillere':row.players}
                for key,label in metric_names.items():
                    avg,lo,hi=(row[f'{key}_{suffix}'] for suffix in ('mean','min','max'))
                    digits=4 if key.startswith('dnp') or key=='point_crps' else 3
                    entry[label]=f'{avg:.{digits}f} [{lo:.{digits}f}–{hi:.{digits}f}]' if pd.notna(avg) else '—'
                view.append(entry)
            return pd.DataFrame(view)
        st.caption('Alle tal nedenfor er gennemsnit [minimum–maksimum] over seeds. n tæller unikke evalueringsrækker, '
                   'ikke gentagelser over seeds. Spændet er simulationsvariation, ikke statistisk usikkerhed på tværs af kampe.')
        st.write('**Alle evalueringsrækker · gennemsnit og seed-spænd**')
        st.dataframe(compact_table(summary[(summary.dimension=='scope')&(summary.group=='all')]),hide_index=True)
        st.write('**Regelmæssig tidligere spilletid · gennemsnit og seed-spænd**')
        st.caption(comparison['group_definitions']['regular_rule'])
        regular_rows=summary[(summary.dimension=='scope')&(summary.group=='regular')]
        st.dataframe(compact_table(regular_rows),hide_index=True)
        baseline_regular=regular_rows[regular_rows.model_version=='component_baseline_v1'].iloc[0]
        for _,candidate in regular_rows[regular_rows.model_version.isin(['component_frequency_025_v1','component_frequency_010_v1'])].iterrows():
            worse=[f'{metric_names[key]}: {candidate[key+"_mean"]-baseline_regular[key+"_mean"]:+.4f}' for key in
                   ('minutes_mae','minutes_rmse','dnp_brier','point_mae','point_rmse','point_crps')
                   if pd.notna(candidate[key+'_mean']) and candidate[key+'_mean']>baseline_regular[key+'_mean']]
            if worse:
                st.warning(f"Regelmæssige spillere · {labels_experiment[candidate['model_version']]}: højere gennemsnitlig fejl end baseline — "+'; '.join(worse)+
                           '. Samlede forbedringer må ikke skjule dette.')
        dimensions={'position':'Position','gameweek':'Gameweek','start_history':'Tidligere starter',
            'minute_history':'Tidligere minutter','regular_position':'Regelmæssige pr. position',
            'position_start_history':'Position × tidligere starter'}
        dimension=st.selectbox('Opdel eksperiment',list(dimensions),format_func=dimensions.get)
        st.dataframe(compact_table(summary[summary.dimension==dimension]),hide_index=True)
        st.caption('Positiv minut-bias = overvurdering. Referencens CRPS er for en punktfordeling og svarer til MAE; '
                   'referencen har ingen kalibreret pointfordeling.')
        with st.expander('Enkelt-seeds og rå gruppemål'):
            selected_seed=st.selectbox('Eksperimentets seed',comparison['seeds'])
            st.dataframe(metrics[metrics.seed==selected_seed],hide_index=True)
        st.write('**Simulationsstøj: parvise forskelle over seeds**')
        sensitivity=pd.DataFrame(comparison['seed_sensitivity'])
        st.dataframe(sensitivity[sensitivity.dimension=='scope'],hide_index=True)
        st.caption('Delta = kandidat minus sammenligningsmodel. Min/max er variationsbredde over seeds, '
                   'ikke konfidensintervaller. Seeds bruger samme base_seed + GW-strategi, men ændrede '
                   'Poisson-parametre betyder, at alle tilfældige træk ikke er parvist identiske.')
        st.download_button('Download prior-eksperiment (JSON)',json.dumps(comparison,ensure_ascii=False),
                           'minutes_comparison.json','application/json')
    else:
        st.info('Ingen gemt sammenligning for dette snapshot. Kør kommandoen med en eksisterende baseline-rapport:')
    st.code('.venv/bin/python scripts/compare_minutes_priors.py --reference-run artifacts/prototype/<kørsel>/report.json',language='bash')

with st.expander('Odds til clean sheets og indkasserede mål · eksperiment',expanded=True):
    st.caption('Separat, valgfri defensiv variant. Spilletid, egne mål/assists og offensive kampjusteringer '
               'er uændrede. Kun clean sheets og pointfradrag for indkasserede mål bruger odds-rater. '
               'component_baseline_v1 er fortsat standard. Ingen historisk GW3–5-evaluering med nye odds.')
    odds_paths=odds_comparison_paths(ROOT/'artifacts/defensive_odds')
    # Prefer real coverage/fallback to the explicitly synthetic demonstration.
    odds_paths=sorted(odds_paths,key=lambda p:read_comparison(str(p))['kind']!='current_forecast_comparison')
    if odds_paths:
        odds_path=st.selectbox('Odds-sammenligning',odds_paths,format_func=lambda p:
            ('SYNTETISK EKSEMPEL · ' if read_comparison(str(p))['kind']!='current_forecast_comparison' else
             'Faktisk dækning · '+read_comparison(str(p))['coverage']['source'].get('source','football_data_uk')+' · ')+p.parent.name)
        odds_report=read_comparison(str(odds_path));oc=odds_report['coverage'];osource=oc['source']
        if odds_report['kind']!='current_forecast_comparison':
            st.warning('SYNTETISK OFFLINE-EKSEMPEL — opdigtede odds på én kamp. Ikke aktuelle bookmakerpriser eller en aktuel oddsprognose.')
        else:
            st.info('Prognosesammenligning, ikke dokumentation for hvilken model der er bedst. Udfaldene kan først evalueres efter runden.')
        source_title={'the_odds_api':'The Odds API','football_data_uk':'Football-Data.co.uk',
                      'synthetic_offline_example':'Syntetisk demonstration'}.get(osource.get('source'),'Football-Data.co.uk')
        st.write(f"**Datakilde: {source_title} · bookmaker: {oc.get('bookmaker','bet365')}**")
        st.write(f"**Odds-dækning: {oc['usable']}/{oc['expected_fixtures']} kampe** · GW {odds_report['event']} · "
                 f"{oc['premier_league_rows']} PL-rækker ud af {oc['total_source_rows']} kilderækker.")
        st.caption(f"Forecast: {odds_report['forecast_origin_at']} · officiel deadline: {odds_report['deadline_at']} · "
                   f"odds hentet: {osource.get('retrieved_at','ukendt')} · available_at: {osource.get('available_at','ukendt')} · publikationstid: ukendt.")
        inputs=odds_report.get('input_sources') or {}
        history_age=inputs.get('history',{}).get('age_hours_at_forecast')
        context_ages=inputs.get('official_context',{}).get('age_hours_at_forecast',{})
        if history_age is not None:
            st.caption(f"Alder ved forecast: spillerhistorik/metadata {history_age:.1f} timer · "
                       f"officiel kamp-/deadlinekontekst {max(context_ages.values()):.1f} timer. "
                       'Priser og skadesstatus kommer fortsat fra historiksnapshot og kan være forældede.')
        st.caption(f"Spillerhistorik fra snapshot {odds_report['source_history_snapshot_id']}. "
                   'Denne gemte sammenligning bruger sine egne kildereferencer og samme konfiguration/seed for begge varianter; sidebarændringer påvirker den ikke.')
        st.write('**Holdmål og clean-sheet-sandsynligheder pr. kamp**')
        fixtures=pd.DataFrame(oc['fixtures'])
        fields=['fixture_id','team_h','team_a','kickoff_time','status','reason','baseline_home_goals','home_goals',
                'baseline_away_goals','away_goals','baseline_home_clean_sheet','home_clean_sheet',
                'baseline_away_clean_sheet','away_clean_sheet']
        st.dataframe(fixtures[fields],hide_index=True)
        st.caption('Clean-sheet-tal er exp(−modstanderens målrate) for hele kampen. Spillerpoint afhænger også af '
                   'minutter og hændelser i spillerens tidsinterval. Tallene er modelafledte, ikke observerede sandheder.')
        with st.expander('Markeder, fitafvigelser og kampmatching'):
            st.write(oc['policy'])
            st.caption('Inverse odds normaliseres separat i hvert komplet marked. To positive målparametre tilpasses '
                       'med ligevægtet least squares mod 1X2 og over/under 2,5; maksimalt tilladt afvigelse 0,06. '
                       'Ingen Max/Avg-blanding, asiatisk handicap eller spillerodds.')
            st.json([f for f in oc['fixtures'] if f['status']=='odds'])
            updates=[]
            for f in oc['fixtures']:
                mp=f.get('market_provenance',{})
                if mp:
                    updates.append(dict(fixture_id=f['fixture_id'],bookmaker=mp['bookmaker'],
                        bookmaker_last_update=mp.get('bookmaker_last_update'),
                        **{k+'_last_update':v for k,v in mp.get('market_last_updates',{}).items()}))
            if updates:
                st.caption('last_update er udbyderens bookmaker-/markedsopdatering. Det er separat fra lokal hentetid og giver ikke historisk tilgængelighed.')
                st.dataframe(pd.DataFrame(updates),hide_index=True)
            st.dataframe(pd.DataFrame(oc['matches']),hide_index=True)
            st.json(osource)
        st.write('**Ændrede spillerprognoser**')
        changes=pd.DataFrame(odds_report['player_changes']).sort_values('xp_delta',key=lambda v:v.abs(),ascending=False)
        st.dataframe(changes,hide_index=True)
        st.caption('Defensive point omfatter clean sheets, indkasserede mål, redninger, defensive bidrag og '
                   'straffesparksredninger. Kun de to første komponenter ændres. minutes_delta skal være nul; '
                   'ændring i samlet xP skal være lig ændringen i defensive point.')
        st.write('**Holdforslag med/uden odds**')
        names={r['player_id']:r['name'] for r in odds_report['baseline']['players']}
        st.dataframe(pd.DataFrame([dict(variant=key,model_version=odds_report[key]['model_version'],
            captain=names[odds_report[key]['team']['captain']],
            squad=', '.join(names[i] for i in odds_report[key]['team']['squad']),
            starters=', '.join(names[i] for i in odds_report[key]['team']['starters']),
            team_mean=odds_report[key]['team_distribution']['mean']) for key in ('baseline','odds_variant')]),hide_index=True)
        st.write('Tilføjet:',[names[i] for i in odds_report['team_changes']['added']],
                 '· Udgået:',[names[i] for i in odds_report['team_changes']['removed']])
        tc=odds_report['team_changes']
        st.write('XI ind:',[names[i] for i in sorted(set(tc['odds_starters'])-set(tc['baseline_starters']))],
                 '· XI ud:',[names[i] for i in sorted(set(tc['baseline_starters'])-set(tc['odds_starters']))])
        st.write(f"Anfører: {names[tc['baseline_captain']]} → {names[tc['odds_captain']]}")
        for limitation in odds_report['limitations']:st.caption(limitation)
        with st.expander('Officiel kontekst og oprindelige historiktidspunkter'):
            st.json(odds_report.get('input_sources'))
        st.download_button('Download odds-sammenligning (JSON)',json.dumps(odds_report,ensure_ascii=False),
                           'defensive_odds_comparison.json','application/json')
    else:
        st.info('Ingen gemt odds-sammenligning. Brug scripts/compare_defensive_odds.py på eksisterende snapshots.')

if 'result' not in st.session_state:
    st.write('Vælg antagelser til venstre, og kør kæden. Den bruger eksisterende snapshots og virker uden FPL-netværksadgang.')
    st.stop()
if st.session_state['signature']!=signature:
    st.warning('Indstillingerne er ændret. Kør igen for at opdatere resultaterne.');st.stop()
report,simulation,totals=st.session_state['result']
st.caption('Kørsel gemt: '+st.session_state['saved_run'])
frame=pd.DataFrame(report['players'])
frame['club']=frame.team_id.map(clubs)
frame['£m']=frame.price/10
frame['position_name']=frame.position.map({1:'GK',2:'DEF',3:'MID',4:'FWD'})
frame['dnp_percent']=100*frame.p_no_play
table_columns={
    'player_id':st.column_config.NumberColumn('FPL-ID',format='%d'),
    'name':'Spiller','club':'Klub','position_name':'Position',
    '£m':st.column_config.NumberColumn('Pris (£m)',format='%.1f'),
    'xp':st.column_config.NumberColumn('Forventede point',format='%.2f'),
    'expected_minutes':st.column_config.NumberColumn('Forventede minutter',format='%.1f'),
    'dnp_percent':st.column_config.NumberColumn('Ingen spilletid (%)',format='%.1f'),
    'basis':'Datagrundlag','fallbacks':'Anvendte tilnærmelser',
}
team=report['team'];dist=report['team_distribution']
columns=st.columns(4)
for col,label,value in zip(columns,['Holdets forventede point','P10 / median / P90','Truppris','Bænkbidrag (autosubs)'],
    [f"{dist['mean']:.1f}",f"{dist['p10']:.0f} / {dist['p50']:.0f} / {dist['p90']:.0f}",f"£{team['cost']:.1f}m",f"{dist['bench_mean']:.2f}"]):
    col.metric(label,value)
st.caption('Holdfordelingen bruger et andet seed end optimeringen. Autosubs og viceanfører beregnes pr. scenarie; '
           'bænkrækkefølge og viceanfører vælges efter xP. Optimeringsmålet bruger en simpel bænkvægt.')
if not team['solver_optimal']: st.warning(f"Solveren returnerede en lovlig, men ikke bevist optimal løsning; gap {team['mip_gap']:.3%}.")
players_tab,squad_tab,eval_tab=st.tabs(['Spillere og fordelinger','Hold og simulation','Evaluering'])
with players_tab:
    display=['player_id','name','club','position_name','£m','xp','expected_minutes','p10','p50','p90','dnp_percent','basis','fallbacks']
    st.dataframe(frame.sort_values('xp',ascending=False)[display],hide_index=True,column_config=table_columns)
    pid=st.selectbox('Pointfordeling for spiller',frame.sort_values('xp',ascending=False).player_id.tolist(),format_func=labels.get)
    i=next(i for i,p in enumerate(simulation.players) if p['id']==pid)
    values,counts=np.unique(simulation.points[:,i],return_counts=True)
    st.bar_chart(pd.DataFrame({'Point':values,'Sandsynlighed':counts/len(simulation.points)}).set_index('Point'))
    st.write('**Spillerforklaring · component_baseline_v1**')
    explanation=report['player_explanations'][pid]
    h=explanation['captured_history']
    st.write(f"Historik: {h['matches']} kampe, {h['minutes']} minutter; "
             f"{h['first_kickoff_at'] or 'ukendt'} → {h['last_kickoff_at'] or 'ukendt'}; GW {h['events']}.")
    st.caption(f"Datagrundlag: {explanation['basis']} · dækning: {explanation['history_coverage']}")
    if explanation['basis']!='player_fixture_history':
        st.warning('Historikfrekvenserne nedenfor beskriver kun de hentede rækker og er ikke en sikker nævner. '
                   'Modellen bruger i stedet sæsonaggregater/proxy eller eksplicitte priors som angivet.')
    st.dataframe(pd.DataFrame([
        {'Udfald':label,'Observeret frekvens':h[field],'Prior':explanation[prior_key],
         'Model før skadesfaktor':before,'Model efter skadesfaktor':explanation[model_key],
         'Betingede minutter (normalfordelingens centrum)':conditional}
        for label,field,prior_key,before,model_key,conditional in [
            ('Start','start_frequency','prior_start',explanation['pre_injury_start'],'p_start',explanation['start_minutes']),
            ('Indhop','sub_frequency','prior_sub',explanation['pre_injury_sub'],'p_sub',explanation['sub_minutes']),
            ('DNP','dnp_frequency','prior_dnp',1-explanation['pre_injury_start']-explanation['pre_injury_sub'],'p_dnp',0)]]),hide_index=True)
    st.caption('Sandsynligheder er pr. kamp. Minutter trækkes fra en afrundet, afklippet normalfordeling '
               '(start: σ=8, 1–90; indhop: σ=9, 1–59). Centret er derfor ikke præcis det simulerede gennemsnit. '
               'Observerede starter forbliver ukendte ved manglende starts; modellens evt. 60-minuttersproxy er en fallback.')
    st.write(f"Frekvensprior: {explanation['frequency_prior_games']}; betingede minutter-prior: {explanation['minutes_prior_games']} kamp(e); "
             f"priorcentre start/indhop: {explanation['conditional_minutes_prior']}. "
             f"Skadesfaktor: {explanation['injury_factor']:.2f}. "
             f"Simuleret GW: {explanation['expected_minutes']:.2f} minutter; DNP {explanation['p_no_play_gw']:.1%}.")
    st.dataframe(pd.DataFrame([{'Rate':label,**explanation['rates'][key]}
                              for label,key in [('xG → mål','goals'),('xA → assists','assists')]]),hide_index=True)
    st.caption('Observeret pr. 90 bruger kun minutter i rækker med kendt felt; ukendt er ikke nul. '
               'Udglatning = (observeret sum + prior_90s × prior_per90) / (eksponering + prior_90s). '
               'Aggregate-fallback bruger i stedet bootstrap-sæsonsummer; de er ikke kampvis historik.')
    st.write('**Hold- og modstanderjustering pr. kamp**')
    st.dataframe(pd.DataFrame(explanation['fixtures']),hide_index=True)
    st.caption('Målmiddel = venue_goal_base × team_attack × opponent_defence, afklippet til [0,15; 4,5]. '
               'Offensiv faktor = målmiddel / league_goal_base × attack_scale, anvendt på både xG- og xA-raten.')
    st.write('**Forventede pointkomponenter · samme simulation**')
    component_names={'appearance':'Spilletid','goals':'Mål','assists':'Assists','clean_sheets':'Clean sheets',
        'goals_conceded':'Indkasserede mål','saves':'Redninger','defensive_contribution':'Defensive bidrag',
        'penalties_saved':'Straffesparksredninger','penalties_missed':'Brændte straffespark',
        'yellow_cards':'Gule kort','red_cards':'Røde kort','own_goals':'Selvmål','bonus':'Bonus'}
    st.dataframe(pd.DataFrame([{'Komponent':component_names[k],'Point':v}
        for k,v in explanation['point_components'].items()]+[
        {'Komponent':'Total','Point':explanation['expected_points']}]),hide_index=True)
    st.caption(f"Afstemningsdifference: {sum(explanation['point_components'].values())-explanation['expected_points']:.12f}. "
               'Alle værdier er gennemsnit af de samme scenarier; ingen ny simulation til forklaringen.')
    st.write('Fallback-antagelser: '+(', '.join(explanation['fallbacks']) or 'Ingen'))
    st.download_button('Download spillertabel (CSV)',frame.to_csv(index=False),'players.csv','text/csv')
with squad_tab:
    order=team['starters']+team['bench']
    selected=frame.set_index('player_id').loc[order].reset_index()
    selected['valg']=['XI']*11+['Bænk GK','Bænk 1','Bænk 2','Bænk 3']
    selected.loc[selected.player_id==team['captain'],'valg']='Anfører'
    selected.loc[selected.player_id==team['vice_captain'],'valg']='Viceanfører'
    st.dataframe(selected[['valg','name','club','position_name','£m','xp','dnp_percent']],hide_index=True,column_config=table_columns)
    values,counts=np.unique(totals['points'],return_counts=True)
    st.bar_chart(pd.DataFrame({'Holdpoint':values,'Sandsynlighed':counts/len(totals['points'])}).set_index('Holdpoint'))
with eval_tab:
    evaluation=report['evaluation']
    st.warning('Retrospektiv evaluering med begrænset tidsprovenance. Ikke en prospektiv test og ikke evidens for kalibrering.')
    if evaluation['n']:
        st.write(f"{evaluation['player_count']} spillere · {evaluation['n']} spiller-GW-observationer · "
                 f"{len(evaluation['gameweeks'])} gameweeks ({', '.join(map(str,evaluation['gameweeks']))}). "
                 'Samme rækker for begge metoder; mindst to tidligere kampe og kontrolleret historikdækning.')
        st.dataframe(pd.DataFrame([{'Metode':'Komponentbaseline',**evaluation['model']},
                                   {'Metode':'Tidligere pointgennemsnit',**evaluation['reference']}]),hide_index=True)
        for title,key,group in [('Pr. position','by_position','position'),('Pr. gameweek','by_gameweek','event')]:
            st.write('**'+title+'**')
            grouped=[]
            for row in evaluation[key]:
                for method in ('model','reference'):
                    grouped.append({group:row[group],'Metode':method,'n':row['n'],**row[method]})
            st.dataframe(pd.DataFrame(grouped),hide_index=True)
        minutes=evaluation['minutes'];dnp=evaluation['dnp']
        st.write(f"**Minutter:** MAE {minutes['mae']:.2f} / RMSE {minutes['rmse']:.2f}; "
                 f"reference MAE {minutes['reference']['mae']:.2f} / RMSE {minutes['reference']['rmse']:.2f}.")
        st.write(f"**Ingen spilletid:** Brier {dnp['brier']:.4f}; reference {dnp['reference_brier']:.4f}. "
                 f"Forventet andel {dnp['predicted_rate']:.1%}, observeret {dnp['observed_rate']:.1%}. Lavere Brier er bedre.")
        st.dataframe(pd.DataFrame(dnp['bins']),hide_index=True)
        st.write('**Minutdiagnostik · grupper fra historik før forecast**')
        diagnostic=evaluation['minute_diagnostics']
        st.caption('Regelmæssig tidligere spilletid: mindst 2 tidligere kampe, gennemsnit ≥60 minutter '
                   'og spilletid i ≥75 % af kampene. Hele puljen betyder alle evaluerbare rækker; '
                   'spillere med utilstrækkelig historik er stadig udeladt. Positiv bias = overvurdering.')
        groups=[dict(group='Hele evalueringspuljen',**diagnostic['scopes']['all']),
                dict(group='Regelmæssig tidligere spilletid',**diagnostic['scopes']['regular'])]
        for title,rows in [('Pulje',groups),('Minutter pr. position',diagnostic['by_position']),
            ('Tidligere startfrekvens',diagnostic['by_start_history']),('Tidligere gennemsnitsminutter',diagnostic['by_minute_history']),
            ('Regelmæssig spilletid pr. position',diagnostic['regular_by_position']),
            ('Position × tidligere starter',diagnostic['by_position_start_history'])]:
            st.write('**'+title+'**')
            view=[]
            for row in rows:
                for method in ('model','reference'):
                    view.append({k:v for k,v in row.items() if k not in ('model','reference')} |
                                {'metode':method,**(row[method] or {})})
            st.dataframe(pd.DataFrame(view),hide_index=True)
        start_groups={r['group']:r for r in diagnostic['by_start_history']}
        if 'never_started' in start_groups and 'regular_starter' in start_groups:
            reserve=start_groups['never_started'];regular=start_groups['regular_starter']
            st.write(f"Ingen tidligere starter: bias {reserve['model']['bias']:+.2f} minutter; "
                     f"modellen giver {reserve['model_start']:.1%} startchance mod {reserve['observed_start']:.1%} tidligere. "
                     f"Regelmæssige startere: bias {regular['model']['bias']:+.2f}; "
                     f"model {regular['model_start']:.1%} mod {regular['observed_start']:.1%} tidligere.")
        st.caption('Fælles prior trækker start-/indhopfrekvenser mod 45 % / 10 % ved standardindstillinger. '
                   'Det kan løfte reserver og sænke faste startere. Kort historik, skiftende roller, '
                   'manglende historiske skadesoplysninger og afklipning af minutter kan også bidrage. '
                   'Anbefalet næste enkeltændring: afprøv en svagere fælles frekvensprior, mens '
                   'prioren for betingede minutter fastholdes. Ingen variant eller tuning er implementeret.')
        st.caption('Startergrupper: never_started = 0 %, occasional_starter = >0 og <75 %, '
                   'regular_starter = ≥75 %; manglende starts vises separat. Minutgrupper: 0; (0,30); [30,60); ≥60. '
                   'observed_start/sub er tidligere frekvenser; model_start/sub er udglattede sandsynligheder pr. kamp, '
                   'ikke observerede udfald i mål-GW. Bias/MAE/RMSE måles i GW-minutter på identiske rækker.')
        with st.expander('Evalueringsrækker og udeladelser'):
            st.dataframe(pd.DataFrame(evaluation['rows']),hide_index=True)
            st.write(evaluation['excluded_counts'])
            st.dataframe(pd.DataFrame(evaluation['excluded']),hide_index=True)
    else: st.info('Utilstrækkelig final spillerhistorik til en sammenligning. Resten af prototypen er tilgængelig.')
    for limitation in evaluation['limitations']: st.caption(limitation)
with st.expander('Antagelser og afgrænsning'):
    st.write('Spilletid: start/indskiftning/DNP med udglattede frekvenser. xG/xA og øvrige hændelser: '
             'Poisson-rater udglattet mod eksplicitte positionspriors. Manglende felter vises i fallback-kolonnen.')
    st.write('Risiko for dobbelt holdstyrke: spillerens historiske xG/xA pr. 90 afspejler allerede eget holds '
             'angreb og de tidligere modstandere. Multiplikation med eget holds angrebsstyrke kan forstærke dette igen. '
             'Modstander-/hjemmejusteringen er relativ til et ligagennemsnit, ikke spillerens historiske kampmix. '
             'Priors og kort historik dæmper, men fjerner ikke risikoen. Formlen er uændret; dette er en strukturel '
             'risiko, ikke et målt bevis på dobbeltregning.')
    for limitation in report['limitations']: st.write('• '+limitation)
st.download_button('Download kørsel (JSON)',json.dumps(report,indent=2,ensure_ascii=False),'forecast.json','application/json')
