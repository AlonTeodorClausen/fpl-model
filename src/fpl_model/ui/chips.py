"""Manual chip inventory and schedule; never activates chips on FPL."""
from datetime import datetime,timezone
import json
import streamlit as st
from fpl_model.chips import CHIPS,LABELS,REBUILDS,normalize_chip_inventory


def _confirmation(key,value):
    stamp_key='owned_chip_confirmation_'+key
    previous=st.session_state.get(stamp_key)
    if previous is None or previous[0]!=value:
        previous=(value,datetime.now(timezone.utc).isoformat())
        st.session_state[stamp_key]=previous
    return previous[1]


def render_chip_inventory(profile,data):
    base=dict(profile,season=profile.get('season',data['season']))
    inv=normalize_chip_inventory(base)
    with st.expander('Mine chips · status og allerede foretagne transfers'):
        st.caption('Bekræft hvilke chips du har tilbage. Offentlig holdimport beviser ikke din fulde chiphistorik. Ændringer gemmes kun med Gem hold.')
        st.session_state.setdefault('owned_chip_start',inv.get('entry_start_event'))
        inv['entry_start_event']=st.number_input('Min første GW i sæsonen',min_value=1,max_value=38,value=None,step=1,key='owned_chip_start')
        for half,label in [('first','Første sæt · GW1–19'),('second','Andet sæt · GW20–38')]:
            st.write(f'**{label}**')
            cols=st.columns(4)
            for col,name in zip(cols,CHIPS):
                row=inv['halves'][half][name];key=f'owned_chip_{half}_{name}'
                st.session_state.setdefault(key,row['status'])
                status=col.selectbox(f'{LABELS[name]} · {label}', ['unknown','available','used'],key=key,
                    format_func=lambda x:{'unknown':'Ikke bekræftet','available':'Til rådighed','used':'Brugt'}[x])
                used=None
                if status=='used':
                    st.session_state.setdefault(key+'_gw',row.get('used_event'))
                    used=col.number_input(f'Brugt GW · {LABELS[name]} · {half}',min_value=1 if half=='first' else 20,
                        max_value=19 if half=='first' else 38,value=None,step=1,key=key+'_gw')
                if status!=row['status'] or used!=row.get('used_event'):
                    row.update(status=status,used_event=used,source='manual',confirmed_at=_confirmation(key,(status,used)))
        active=inv.get('active_chip')
        st.session_state.setdefault('owned_chip_active',active['name'] if active else None)
        active_name=st.selectbox('Allerede aktiv chip på FPL', [None]+list(CHIPS),key='owned_chip_active',format_func=lambda c:LABELS.get(c,'Ingen'))
        if active_name:
            st.session_state.setdefault('owned_chip_active_event',active['event'] if active else None)
            active_event=st.number_input('GW for aktiv chip',min_value=1,max_value=38,value=None,step=1,key='owned_chip_active_event')
            inv['active_chip']=dict(name=active_name,event=active_event)
            if active_event is not None:
                h='first' if active_event<=19 else 'second'
                row=inv['halves'][h][active_name]
                if row['status']!='used' or row.get('used_event')!=active_event:
                    row.update(status='used',used_event=active_event,source='manual_active_chip',confirmed_at=_confirmation('active',(active_name,active_event)))
        else:inv['active_chip']=None
        st.caption('En aktiv chip er bindende i beregningen. Appen foretager ingen handlinger på din FPL-konto.')
        st.write('**Hvis du allerede har lavet transfers før Wildcard/Free Hit**')
        st.caption('Vi skal kende tilstanden før ugens handler. Udfyld kun verificerede værdier; almindelige forslag kræver ikke dette felt.')
        st.code('{"event": 7, "bank": 10, "free_transfers": 2, "existing_hits": 0,\n "players": [{"player_id": 123, "selling_price": 75}, "… alle 15 …"]}',language='json')
        st.caption('Bank og salgsværdier er i £0,1m: 10 = £1,0m. Brug officielle spiller-ID’er fra holdeditoren.')
        state=profile.get('pre_transfer_state')
        st.session_state.setdefault('owned_chip_pre_json',json.dumps(state,ensure_ascii=False,indent=2) if state else '')
        raw=st.text_area('Bekræftet tilstand før ugens transfers (JSON)',key='owned_chip_pre_json')
        if raw.strip():
            state=json.loads(raw)
            if not isinstance(state,dict):raise ValueError('Tilstanden før transfers skal være et JSON-objekt.')
            if not state.get('confirmed_at'):
                if st.checkbox('Jeg bekræfter oplysningerne før ugens transfers',key='owned_chip_confirm_pre'):state['confirmed_at']=_confirmation('pre',raw)
        else:state=None
    result=dict(chip_inventory=inv)
    if state:result['pre_transfer_state']=state
    return result


def render_chip_schedule(profile,events,data,origin_at):
    inv=normalize_chip_inventory(profile);plan={};active=inv.get('active_chip')
    with st.expander('Chips i denne plan · vælg uge',expanded=False):
        st.caption('Manuelt chipvalg i 1–4 GWs. Automatisk chipstrategi frem til GW19 er endnu ikke implementeret.')
        deadline=next((e['deadline_time'] for e in data['events'] if e['id']==19),None)
        st.write('Første sæt udløber ved GW19-deadlinen: '+(deadline or 'ikke tilgængelig i dette snapshot'))
        for event in events:
            half='first' if event<=19 else 'second'
            options=[None]+[c for c in CHIPS if inv['halves'][half][c]['status']=='available']
            binding=active and active['event']==event
            if binding:
                options=[active['name']];st.info(f"GW{event}: {LABELS[active['name']]} er allerede aktiv.")
            key=f'owned_chip_schedule_{event}'
            if st.session_state.get(key) not in options:st.session_state[key]=options[0]
            choice=st.selectbox(f'Chip · GW{event}',options,key=key,format_func=lambda c:LABELS.get(c,'Ingen chip'),disabled=bool(binding))
            if choice:plan[event]=choice
        if not any(r['status']=='available' for h in inv['halves'].values() for r in h.values()):
            st.caption('Ingen bekræftede ledige chips. Ret status under Redigér hold → Mine chips.')
        if plan:st.caption('Sammenlignes med samme prognoser uden chips. WC/FH-omlægninger er uden for grænsen for almindelige transfers.')
    return plan
