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
from fpl_model.prototype import run_prototype

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
    minute_prior=st.number_input('Spilletids-prior: kampe',min_value=.1,max_value=20.,value=1.,step=.5)
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
signature=(str(chosen),event,budget,draws,int(seed),config,tuple(locked),tuple(excluded),bench_weight)
if st.button('Kør prognose, simulation og optimering',type='primary'):
    try:
        with st.spinner('Simulerer spillere, vælger lovligt hold og evaluerer i nye scenarier …'):
            result=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,
                                  locked=locked,excluded=excluded,bench_weight=bench_weight)
        st.session_state['result']=result;st.session_state['signature']=signature
    except (ValueError,RuntimeError) as exc:
        st.error(str(exc))
        st.session_state.pop('result',None)
if 'result' not in st.session_state:
    st.write('Vælg antagelser til venstre, og kør kæden. Den bruger eksisterende snapshots og virker uden FPL-netværksadgang.')
    st.stop()
if st.session_state['signature']!=signature:
    st.warning('Indstillingerne er ændret. Kør igen for at opdatere resultaterne.');st.stop()
report,simulation,totals=st.session_state['result']
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
players_tab,squad_tab,eval_tab=st.tabs(['Spillere og fordelinger','Hold og simulation','Første evaluering'])
with players_tab:
    display=['player_id','name','club','position_name','£m','xp','expected_minutes','p10','p50','p90','dnp_percent','basis','fallbacks']
    st.dataframe(frame.sort_values('xp',ascending=False)[display],hide_index=True,column_config=table_columns)
    pid=st.selectbox('Pointfordeling for spiller',frame.sort_values('xp',ascending=False).player_id.tolist(),format_func=labels.get)
    i=next(i for i,p in enumerate(simulation.players) if p['id']==pid)
    values,counts=np.unique(simulation.points[:,i],return_counts=True)
    st.bar_chart(pd.DataFrame({'Point':values,'Sandsynlighed':counts/len(simulation.points)}).set_index('Point'))
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
    st.warning('Retrospektiv mini-evaluering med begrænset tidsprovenance. Ikke en prospektiv test og ikke evidens for kalibrering.')
    if evaluation['n']:
        st.write(f"{evaluation['n']} spiller-GW-observationer. Mindst to tidligere kampobservationer før hver test-GW.")
        st.dataframe(pd.DataFrame([{'Metode':'Komponentbaseline',**evaluation['model']},
                                   {'Metode':'Tidligere pointgennemsnit',**evaluation['reference']}]),hide_index=True)
        st.dataframe(pd.DataFrame(evaluation['rows']),hide_index=True)
    else: st.info('Utilstrækkelig final spillerhistorik til en sammenligning. Resten af prototypen er tilgængelig.')
    for limitation in evaluation['limitations']: st.caption(limitation)
with st.expander('Antagelser og afgrænsning'):
    st.write('Spilletid: start/indskiftning/DNP med udglattede frekvenser. xG/xA og øvrige hændelser: '
             'Poisson-rater udglattet mod eksplicitte positionspriors. Manglende felter vises i fallback-kolonnen.')
    for limitation in report['limitations']: st.write('• '+limitation)
st.download_button('Download kørsel (JSON)',json.dumps(report,indent=2,ensure_ascii=False),'forecast.json','application/json')
