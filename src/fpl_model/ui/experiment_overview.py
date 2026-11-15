"""Single overview of model experiments on the analysis page."""
import pandas as pd
import streamlit as st

from fpl_model.experiment_overview import overview_rows


def show_experiment_overview():
    st.subheader('Modelforsøg · status')
    st.caption('Ét overblik over alle forsøg. Pensionerede forsøg kan ikke længere vælges, men deres kode, '
               'rapporter og noter ligger i git-historikken, og gemte forslag, der brugte dem, kan stadig åbnes.')
    frame = pd.DataFrame([dict(Forsøg=r['name'], Status=r['status'], Ændrer=r['changes'],
                               Resultat=r['result']) for r in overview_rows()])
    st.dataframe(frame, hide_index=True, use_container_width=True)
