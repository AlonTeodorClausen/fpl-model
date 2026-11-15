"""FPL Lab: personal team first, experiments on a secondary page."""
from pathlib import Path
import runpy
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
st.set_page_config(page_title='FPL Lab · Mit hold', page_icon='⚽', layout='wide')
from fpl_model.ui.presentation import apply_theme
from fpl_model.ui.guest_state import guest_mode
apply_theme()
with st.sidebar:
    st.html('<div class="lab-brand">FPL<span> / </span>LAB</div>')
    st.caption('DIT HOLD. DIN NÆSTE BESLUTNING.')
page = st.sidebar.radio('Side', ['Mit hold', 'Model'] if guest_mode() else
                        ['Mit hold', 'Model', 'Analyse og eksperimenter'])
if page == 'Mit hold':
    from fpl_model.ui.my_team import render
    render()
elif page == 'Model':
    from fpl_model.ui.model_guide import render
    render()
else:
    view=st.sidebar.radio('Analysevisning',['Prognoser og evaluering','Transferlaboratorium'])
    if view=='Transferlaboratorium':
        from fpl_model.ui.my_team import render
        render(experimental_mode=True)
    else:
        runpy.run_path(str(ROOT/'src/fpl_model/ui/experiments.py'))
