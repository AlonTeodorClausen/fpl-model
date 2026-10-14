"""ID/link → public deadline squad preview → explicit local draft."""
import pandas as pd
import streamlit as st
from fpl_model.team_import import capture_team,make_draft
from fpl_model.my_team import load_profile


def render_import(data,root,apply_draft):
    st.subheader('Hent dit hold fra FPL')
    known=st.session_state.get('team_draft',{}).get('import_provenance',{})
    value=st.text_input('Hold-ID eller FPL-link',value=str(known.get('entry_id','')),
                        placeholder='3533723 eller https://fantasy.premierleague.com/entry/3533723/event/6',key='team_import_id')
    st.caption('Find dit ID i adressen på FPL’s pointside. Ingen adgangskode eller login kræves.')
    if st.button('Hent hold fra FPL',type='primary'):
        st.session_state.pop('team_import_preview',None)
        try:
            with st.spinner('Henter den seneste offentlige opstilling …'):
                st.session_state['team_import_preview']=capture_team(value,root/'data/raw')
        except (ValueError,OSError) as exc:st.error(str(exc))
    imported=st.session_state.get('team_import_preview')
    if imported:
        st.write(f"**{imported['name']}** · hold #{imported['entry_id']} · offentlig opstilling fra **GW{imported['event']}**")
        st.caption(f"Hentet {imported['observed_at']} · deadline {imported['deadline_at']}")
        st.warning('Dette er holdet fra den seneste offentlige deadline. Transfers foretaget bagefter er ikke med. '
                   'Salgsværdier og resterende gratis transfers er ikke offentlige; kontrollér også bank før du planlægger.')
        by_id={p['id']:p for p in imported['players']}
        positions={1:'Målmand',2:'Forsvarer',3:'Midtbane',4:'Angriber'}
        st.dataframe(pd.DataFrame([dict(Spiller=by_id[p['element']]['web_name'],
            Position=positions[by_id[p['element']]['element_type']],
            Rolle=('XI' if p['position']<=11 else 'Bænk')+(' · anfører' if p.get('is_captain') else ' · vice' if p.get('is_vice_captain') else ''),
            **{'Aktuel købspris £m':by_id[p['element']]['now_cost']/10}) for p in imported['picks']]),hide_index=True)
        previous=None;path=root/'data/processed/my_team.json'
        if path.exists():
            try:previous=load_profile(path)
            except (ValueError,OSError,KeyError):pass
        same=bool(previous and previous['season']==data['season'] and
                  {p['player_id'] for p in previous['players']}==set(by_id))
        keep=st.checkbox('Genbrug mine gemte salgsværdier, bank og transfers (jeg har kontrolleret dem)',value=False) if same else False
        if not keep:
            bank=imported['bank_at_deadline']
            st.caption(f"Bank ved GW{imported['event']}-deadline: "+(f'£{bank/10:.1f}m.' if bank is not None else 'ukendt.')+
                       ' Salgsværdier, gratis transfers og transfers siden deadline skal udfyldes nedenfor.')
        try:
            draft=make_draft(imported,data,previous=previous,keep_existing=keep)
        except ValueError as exc:st.error(str(exc))
        else:
            if st.button('Brug dette hold'):
                apply_draft(draft)
                st.success('Spillerne er indlæst nedenfor. Kontrollér økonomien og tryk Gem hold. Dit tidligere gemte hold er bevaret indtil da.')
    provenance=st.session_state.get('team_draft',{}).get('import_provenance')
    if provenance:
        st.caption(f"Indlæst fra FPL #{provenance['entry_id']}, GW{provenance['event']} · ikke en live-synkronisering af transfers efter deadline.")
