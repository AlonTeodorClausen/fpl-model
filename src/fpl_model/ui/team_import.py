"""ID/link → public deadline squad preview → explicit local draft."""
import pandas as pd
import streamlit as st
from fpl_model.team_import import capture_team,make_draft,parse_team_id
from fpl_model.my_team import load_profile
from fpl_model.ui.guest_state import guest_root
from fpl_model.ui.guest_limits import GuestLimitError,claim_guest_job
from fpl_model.ui.presentation import friendly_time


def render_import(data,root,apply_draft,*,guest=False):
    st.markdown('**Hent dit hold fra FPL**')
    known=st.session_state.get('team_draft',{}).get('import_provenance',{})
    value=st.text_input('Hold-ID eller FPL-link',value=str(known.get('entry_id','')),
                        placeholder='Fx 3533723',key='team_import_id',
                        help='Find ID’et i adressen på FPL’s pointside. Offentlige hold kræver ikke login.')
    if st.button('Hent hold fra FPL',type='primary'):
        st.session_state.pop('team_import_preview',None)
        permit=None
        try:
            if guest:
                parse_team_id(value)
                permit=claim_guest_job('import')
            with st.spinner('Henter den seneste offentlige opstilling …'):
                capture_root=guest_root() if guest else root
                st.session_state['team_import_preview']=capture_team(value,capture_root/'data/raw')
        except GuestLimitError as exc:st.warning(str(exc))
        except (ValueError,OSError) as exc:st.error(str(exc))
        finally:
            if permit is not None:permit.release()
    imported=st.session_state.get('team_import_preview')
    if imported:
        st.write(f"**{imported['name']}** · hold #{imported['entry_id']} · offentlig opstilling fra **GW{imported['event']}**")
        st.caption(f"Hentet {friendly_time(imported['observed_at'])} · GW-frist {friendly_time(imported['deadline_at'])} (dansk tid)")
        st.warning('FPL viser holdet ved den seneste deadline. Har du lavet transfers siden, skal du rette holdet. '
                   'Kontrollér også bank, gratis transfers og salgsværdier, før du gemmer.')
        by_id={p['id']:p for p in imported['players']}
        positions={1:'Målmand',2:'Forsvarer',3:'Midtbane',4:'Angriber'}
        with st.expander('Se de 15 spillere fra FPL'):
            st.dataframe(pd.DataFrame([dict(Spiller=by_id[p['element']]['web_name'],
                Position=positions[by_id[p['element']]['element_type']],
                Rolle=('XI' if p['position']<=11 else 'Bænk')+(' · anfører' if p.get('is_captain') else ' · vice' if p.get('is_vice_captain') else ''),
                **{'Aktuel listepris £m':by_id[p['element']]['now_cost']/10}) for p in imported['picks']]),hide_index=True)
        previous=st.session_state.get('team_draft') if guest else None
        if not guest:
            path=root/'data/processed/my_team.json'
            if path.exists():
                try:previous=load_profile(path)
                except (ValueError,OSError,KeyError):pass
        same=bool(previous and previous['season']==data['season'] and
                  {p['player_id'] for p in previous['players']}==set(by_id))
        keep=st.checkbox('Bevar mine tidligere lokale salgsværdier, bank og transferstatus',value=True) if same else False
        if not keep:
            bank=imported['bank_at_deadline']
            st.caption(f"Bank ved GW{imported['event']}-deadline: "+(f'£{bank/10:.1f}m.' if bank is not None else 'ukendt.')+
                       ' Aktuel bank, gratis transfers og transfers siden deadline skal udfyldes nedenfor.')
        try:
            draft=make_draft(imported,data,previous=previous,keep_existing=keep)
        except ValueError as exc:st.error(str(exc))
        else:
            estimates=draft.get('price_estimate_ids',[])
            if estimates:
                st.warning(f'{len(estimates)} salgsværdier er estimater. Vi bruger højst den aktuelle listepris som udgangspunkt; '
                           'det kan overvurdere dit reelle transferbudget. Kontrollér salgsværdien i FPL, før du gennemfører foreslåede transfers.')
            if imported['observed_at']!=data.get('as_of_at') and any(
                by_id[i]['now_cost']!=next(p['now_cost'] for p in data['players'] if p['id']==i)
                for i in by_id):
                st.caption('Nogle listepriser er ændret siden det valgte prognosedatagrundlag. '
                           'Brug Hent seneste data for at opdatere modelpriserne.')
            if st.button('Brug dette hold'):
                apply_draft(draft)
                st.session_state['editor_expand_once']=True
                st.success('Holdet er indlæst. Angiv aktuel bank og transferstatus, ret eventuelle salgsværdier og tryk Gem hold. '
                           'Dit tidligere gemte hold er bevaret indtil da.')
    provenance=st.session_state.get('team_draft',{}).get('import_provenance')
    if provenance:
        st.caption(f"Indlæst fra FPL · GW{provenance['event']}. Kontrollér transfers siden fristen.")
