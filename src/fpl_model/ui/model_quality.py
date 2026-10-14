"""Optional model settings and saved forecast evaluation, no implicit downloads."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st


def role_controls(data,events,labels):
    records=[]
    with st.expander('Eksperiment · startchance og begrænsede returminutter'):
        st.caption('Tilgængelighed styres separat i skadeafsnittet. Disse oplysninger ændrer kun rollen, hvis spilleren er tilgængelig. Ingen sandsynlighed eller returdato udledes af fri nyhedstekst.')
        selected=st.multiselect('Spillere med dokumenteret/antaget rollebegrænsning',sorted(labels,key=labels.get),format_func=labels.get)
        for pid in selected:
            reason=st.text_input(f'Begrundelse for returrolle · {labels[pid]}',key=f'role_reason_{pid}')
            source=st.text_input(f'Kilde til returrolle (valgfrit) · {labels[pid]}',key=f'role_source_{pid}')
            for event in events:
                st.write(f'{labels[pid]} · GW{event}')
                start=st.number_input('Startchance givet tilgængelig (0–1)',min_value=0.,max_value=1.,value=None,step=.05,key=f'role_start_{pid}_{event}')
                cap=st.number_input('Maksimale minutter ved start',min_value=1,max_value=90,value=None,step=1,key=f'role_cap_{pid}_{event}')
                sub=st.number_input('Maksimale minutter ved indhop',min_value=1,max_value=59,value=None,step=1,key=f'role_sub_{pid}_{event}')
                if any(x is not None for x in (start,cap,sub)):
                    records.append(dict(player_id=pid,event=event,start_given_available=start,start_minutes_cap=cap,
                        sub_minutes_cap=sub,reason=reason,source_url=source or None,kind='manual_sourced_assumption'))
        st.caption('Tomme felter bevarer modellen. Begrundelse er påkrævet; en kilde gør ikke den indtastede sandsynlighed til et verificeret faktum.')
    return records


def show_model_quality(root,data):
    from fpl_model.ui.assists import show_assist_comparison
    show_assist_comparison(root)
    from fpl_model.ui.season_priors import show_season_prior_comparison
    show_season_prior_comparison(root)
    from fpl_model.ui.bonus import show_bonus_comparison
    show_bonus_comparison(root)
    from fpl_model.ui.set_pieces import show_set_piece_comparison
    show_set_piece_comparison(root)
    show_role_comparison(root)
    from fpl_model.prediction_evaluation import load_forecasts,evaluate_saved
    with st.expander('Modeludvikling · gemte prognoser og faktisk efterkontrol'):
        st.caption('Baseline er reference. Retrospektiv udviklingsdiagnostik og faktisk før-deadline-evaluering holdes adskilt. Ingen downloads eller nye simulationer sker her.')
        paths=sorted((Path(root)/'artifacts/model_forecasts').glob('*/forecast.json'),reverse=True)
        if not paths:
            st.info('Ingen gemte modelprognoser endnu. Kør scripts/run_model_evolution.py med eksisterende snapshots.');return
        chosen=st.selectbox('Gemt modelprognose',paths,format_func=lambda p:p.parent.name)
        try:report,arrays=load_forecasts(chosen.parent)
        except (ValueError,OSError) as exc:st.error(str(exc));return
        st.write(f"GW{report['event']} · prognose {report['forecast_origin_at']} · gemt {report['created_at']} · deadline {report['deadline_at']}")
        st.write('Proveniensstatus:',report['provenance_status'])
        source=report.get('input_sources',{}).get('history',{})
        st.caption(f"Officielle data: {source.get('available_at','se råreferencer')} · snapshot {source.get('snapshot_id','ukendt')}")
        c=report.get('coverage')
        if c:st.write(f"Odds: {c['usable']}/{c['expected_fixtures']} · observeret {c['source'].get('available_at','ukendt')}")
        names=list(report['variants'])
        selected=st.selectbox('Modelvariant – forklaring',names)
        variant=report['variants'][selected]
        st.dataframe(pd.DataFrame(variant['players']),hide_index=True)
        pool={r['player_id']:r['name'] for r in variant['players']}
        pid=st.selectbox('Spiller – rolle og point',sorted(pool),format_func=pool.get)
        e=variant['explanations'][str(pid)]
        st.write('Rolle:',e.get('role',{'method':'baseline_v1'}))
        st.write('Tilgængelighed:',e.get('availability',{'probability':e['injury_factor']}))
        st.write(f"Start {e['p_start']:.1%} · indhop {e['p_sub']:.1%} · DNP {e['p_no_play_gw']:.1%} · minutter {e['expected_minutes']:.1f}")
        st.dataframe(pd.DataFrame([dict(komponent=k,point=v) for k,v in e['point_components'].items()]),hide_index=True)
        st.write('Fælles mål – afstemning:',variant.get('match_audit',[]))
        for limitation in report['limitations']:st.caption(limitation)
        diagnosis=chosen.parent/'development.json'
        if diagnosis.exists():
            dev=json.loads(diagnosis.read_text())
            st.warning('Retrospektive udviklingsdata, ikke uafhængig test. Samme evalueringsrækker; ingen aktuelle odds/skader i historiske inputs.')
            rows=[]
            for name,r in dev.items():
                if not r.get('n'):continue
                rows.append(dict(model=name,n=r['n'],minut_MAE=r['minutes']['mae'],minut_RMSE=r['minutes']['rmse'],
                    DNP_Brier=r['dnp']['brier'],point_MAE=r['model']['mae'],point_RMSE=r['model']['rmse'],CRPS=r['model']['crps']))
            baseline=dev.get('baseline',{})
            if baseline.get('n'):
                rows.append(dict(model='Tidligere gennemsnit (reference)',n=baseline['n'],
                    minut_MAE=baseline['minutes']['reference']['mae'],minut_RMSE=baseline['minutes']['reference']['rmse'],
                    DNP_Brier=baseline['dnp']['reference_brier'],point_MAE=baseline['reference']['mae'],
                    point_RMSE=baseline['reference']['rmse'],CRPS=None))
            st.dataframe(pd.DataFrame(rows),hide_index=True)
            groups=[]
            for name,r in dev.items():
                for scope,values in r['minute_diagnostics']['scopes'].items():
                    if values['model']:
                        groups.append(dict(model=name,gruppe=scope,n=values['n'],**values['model']))
            st.dataframe(pd.DataFrame(groups),hide_index=True)
            b=baseline.get('minute_diagnostics',{}).get('scopes',{}).get('regular',{}).get('model')
            c=dev.get('recent_role',{}).get('minute_diagnostics',{}).get('scopes',{}).get('regular',{}).get('model')
            if b and c and c['mae']>b['mae']:
                st.warning(f"Regelmæssige spillere forværres: minut-MAE {b['mae']:.2f} → {c['mae']:.2f}. En samlet forbedring er ikke tilstrækkelig til at vælge ny standard.")
            with st.expander('Udviklingsdiagnostik pr. position og GW'):
                for key in ('by_position','by_gameweek'):
                    st.dataframe(pd.DataFrame([dict(variant=name,**r) for name,v in dev.items() for r in v[key]]),hide_index=True)
                st.write('Historikbaserede grupper:',{k:v['minute_diagnostics'] for k,v in dev.items()})
        if st.button('Efterkontrollér mod indlæste officielle slutresultater'):
            try:
                out,result=evaluate_saved(chosen.parent,data['histories'],Path(root)/'artifacts/model_evaluations')
                st.success(f'Efterkontrol gemt lokalt: {out.name}')
                st.session_state['model_outcome_check']=(str(chosen),result)
            except (ValueError,OSError,KeyError) as exc:st.error(str(exc))
        saved=st.session_state.get('model_outcome_check')
        if saved and saved[0]==str(chosen):
            for name,value in saved[1]['variants'].items():
                st.write(name,value['status'],f"{value['n']} spillere med komplette endelige udfald")
                st.write({k:value[k] for k in ('points','minutes','dnp','interval_80','by_position','dnp_calibration')})
                st.dataframe(pd.DataFrame(value['pending']),hide_index=True)
                st.caption('Manglende/provisoriske udfald er afventende, aldrig DNP. Flyttede kampe kræver særskilt afklaring.')


def show_role_comparison(root):
    """Read stored comparisons only; never triggers estimation or a download."""
    import json
    from pathlib import Path
    import pandas as pd
    import streamlit as st
    with st.expander('Rollespecifik spilletid · udviklingssammenligning'):
        paths=sorted((Path(root)/'artifacts/role_minutes').glob('*/comparison.json'),reverse=True)
        if not paths:
            st.info('Ingen gemt sammenligning. Kør scripts/compare_role_minutes.py på et eksisterende snapshot.');return
        chosen=st.selectbox('Gemt rollesammenligning',paths,format_func=lambda p:p.parent.name)
        try:report=json.loads(chosen.read_text())
        except (ValueError,OSError) as exc:st.error(str(exc));return
        meta=report['metadata']
        st.warning('Retrospektive udviklingsdata – ikke uafhængig eller prospektiv test. Baseline er fortsat standard. Ingen odds eller aktuelle skader i historiske inputs.')
        st.caption(f"GW {', '.join(map(str,meta['gameweeks']))} · {meta['draws']} scenarier · seed {meta['seed']} + GW · snapshot {meta['snapshot_id']} · gemt {meta['created_at']}")
        names={'baseline':'Baseline v1','recent_role':'Tidligere rollemodel','role_transitions':'Ny rollespecifik model','reference':'Tidligere gennemsnit'}
        def table(rows):
            return pd.DataFrame([dict(Model=names.get(r['model'],r['model']),**({'Gruppe':r['group']} if 'group' in r else {}),
                n=r['n'],**{k:r.get(k) for k in ('minutes_bias','minutes_mae','minutes_rmse','points_mae','points_rmse','dnp_brier','crps')}) for r in rows])
        st.dataframe(table(report['summary']),hide_index=True)
        st.write('**Hele puljen og regelmæssige spillere skal vurderes hver for sig.**')
        st.caption(report['regular_rule']+' Minut-bias = forventet minus faktisk spilletid.')
        st.dataframe(table(report['by_regular_history']),hide_index=True)
        st.dataframe(table(report['by_role']),hide_index=True)
        b=next(r for r in report['by_regular_history'] if r['group']=='regular' and r['model']=='baseline') if any(r['group']=='regular' for r in report['by_regular_history']) else None
        c=next(r for r in report['by_regular_history'] if r['group']=='regular' and r['model']=='role_transitions') if b else None
        if b and c and c['minutes_mae']>b['minutes_mae']:
            st.warning('Den nye variant forværrer minut-MAE blandt regelmæssige spillere. En samlet forbedring er ikke tilstrækkelig til at vælge ny standard.')
        with st.expander('Position, GW, DNP og antagelser'):
            for key in ('by_position','by_gameweek','by_minute_history'):st.dataframe(table(report[key]),hide_index=True)
            st.dataframe(pd.DataFrame([dict(Model=names[r['model']],n=r['n'],forudsagt_DNP=r['dnp_predicted'],observeret_DNP=r['dnp_observed']) for r in report['summary']]),hide_index=True)
            st.json(meta['candidate_options'])
            for limitation in report['limitations']:st.caption(limitation)
        st.download_button('Download rollesammenligning (JSON)',chosen.read_bytes(),'role_minutes_comparison.json','application/json')
