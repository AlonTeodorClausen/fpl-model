"""Display-only components. Never select players, infer a lineup or compute forecasts."""
from html import escape
import streamlit as st


def _text(value):
    return escape(str(value), quote=True)


def apply_theme():
    st.html('''<style>
    :root { --ink:#142c40; --muted:#617586; --accent:#087f6f; }
    [data-testid="stAppViewContainer"] { background:#f3f6f8; color:var(--ink); }
    [data-testid="stHeader"] { background:rgba(243,246,248,.96); }
    .block-container { max-width:1240px; padding-top:2.5rem; }
    h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; }
    h1 { font-size:2.15rem !important; }
    [data-testid="stSidebar"] { background:#142c40; }
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h2 { color:#edf5f8; }
    [data-testid="stSidebar"] [role="combobox"] { color:#142c40; }
    [data-testid="stExpander"] { background:white; border:1px solid #dce5eb; border-radius:14px; }
    [data-testid="stMetric"] { background:white; padding:16px; border:1px solid #dce5eb; border-radius:12px; }
    [data-testid="stMetricLabel"] { color:var(--muted); }
    [data-testid="stBaseButton-primary"] { background:#087f6f; border-color:#087f6f; border-radius:9px; }
    [data-testid="stBaseButton-secondary"] { border-radius:9px; }
    .lab-metrics { display:grid; grid-template-columns:repeat(var(--count),minmax(0,1fr)); gap:12px; margin:10px 0 22px; }
    .lab-metric { background:white; border:1px solid #dce5eb; border-radius:12px; padding:15px 17px; }
    .lab-metric-label { color:#617586; font-size:12px; }
    .lab-metric-value { font-size:28px; font-weight:750; color:#142c40; letter-spacing:-1px; margin-top:4px; }
    .lab-metric-note { font-size:11px; color:#617586; margin-top:3px; }
    .lab-brand { color:#f4fbff; font-size:24px; font-weight:800; letter-spacing:-1px; padding:12px 0 2px; }
    .lab-brand span { color:#7bdac1; } .lab-kicker { color:#087f6f; font-size:11px; font-weight:800; letter-spacing:2px; text-transform:uppercase; }
    .lab-pitch { background:repeating-linear-gradient(0deg,#176353 0px,#176353 82px,#1a6a59 82px,#1a6a59 164px);
      border:1px solid #105243; border-radius:18px; padding:20px 12px; margin:8px 0 20px; position:relative; overflow:hidden; }
    .lab-pitch:before { content:""; position:absolute; inset:14px; border:1px solid #ffffff30; border-radius:3px; pointer-events:none; }
    .lab-pitch:after { content:""; position:absolute; width:90px; height:90px; border:1px solid #ffffff30;
      border-radius:50%; top:45%; left:calc(50% - 45px); pointer-events:none; }
    .lab-row { display:flex; justify-content:center; gap:10px; position:relative; z-index:1; margin:12px 0 20px; }
    .lab-player { width:132px; min-width:0; text-align:center; }
    .lab-shirt { width:35px; height:35px; margin:0 auto 4px; display:block; background:linear-gradient(90deg,#e2f3ed 40%,#67bba3 40%,#67bba3 60%,#e2f3ed 60%); clip-path:polygon(30% 10%,10% 23%,2% 50%,23% 58%,28% 45%,28% 94%,73% 94%,73% 45%,78% 58%,98% 50%,90% 23%,70% 10%,60% 18%,40% 18%); }
    .lab-player-body { background:#ffffff; border-radius:8px; padding:7px 3px; box-shadow:0 3px 8px #002d2820; }
    .lab-name { font-weight:750; color:#142c40; font-size:13px; overflow-wrap:anywhere; }
    .lab-meta { color:#617586; font-size:11px; margin-top:3px; }
    .lab-stat { color:#087f6f; font-size:12px; font-weight:750; margin-top:3px; }
    .lab-badge { display:inline-block; background:#142c40; color:white; border-radius:12px; padding:1px 5px; font-size:10px; }
    .lab-doubt { color:#895400; background:#fff2ce; border-radius:4px; padding:1px 4px; font-size:10px; }
    .lab-bench { background:#e6edf1; border-radius:12px; padding:8px 12px; margin-bottom:18px; }
    .lab-bench .lab-row { margin:8px 0; } .lab-bench-title { color:#526a7d; font-size:11px; font-weight:800; letter-spacing:1px; }
    .lab-transfer { border:1px solid #dce5eb; border-radius:14px; background:white; padding:18px; margin:8px 0 14px; }
    .lab-transfer-title { font-size:18px; font-weight:750; color:#142c40; margin-bottom:10px; }
    .lab-moves { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
    .lab-out { color:#9b3b44; } .lab-in { color:#087f6f; }
    .lab-note { color:#617586; font-size:12px; margin-top:12px; }
    @media(max-width:640px) { .lab-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; } .lab-metric { padding:12px; } .block-container { padding:1.3rem .8rem; }
      .lab-row { gap:4px; } .lab-pitch { padding:12px 5px; } .lab-name { font-size:11px; }
      .lab-meta { font-size:10px; } .lab-shirt { width:28px; height:28px; } .lab-player-body { padding:6px 2px; }
      .lab-moves { grid-template-columns:1fr; gap:8px; } }
    </style>''')


def pitch_html(players, *, lineup=None):
    """Players use display fields; absence of lineup means positional squad, never XI."""
    pool={p['id']:p for p in players}
    def card(pid,role=''):
        p=pool[pid];badge=''
        if lineup and pid==lineup['captain']:badge=' <span class="lab-badge">C</span>'
        elif lineup and pid==lineup.get('vice_captain'):badge=' <span class="lab-badge">V</span>'
        warning=f' <span class="lab-doubt">{_text(p["flag"])}</span>' if p.get('flag') else ''
        stat=f'<div class="lab-stat">{p["xp"]:.2f} xP · {p["minutes"]:.0f} min</div>' if p.get('xp') is not None and p.get('minutes') is not None else ''
        shirt='<div class="lab-shirt" aria-hidden="true"></div>'
        return f'<div class="lab-player">{shirt}<div class="lab-player-body"><div class="lab-name">{_text(p["name"])}{badge}{warning}</div><div class="lab-meta">{_text(p.get("detail",""))}</div>{stat}<div class="lab-meta">{_text(role)}</div></div></div>'
    ids=lineup['starters'] if lineup else list(pool)
    rows=['<div class="lab-row">'+''.join(card(i) for i in ids if pool[i]['position']==pos)+'</div>' for pos in range(1,5)]
    html='<div class="lab-pitch" role="group" aria-label="'+('Startellever' if lineup else 'Trup efter position, ikke en startellever')+'">'+''.join(rows)+'</div>'
    if lineup:
        bench=''.join(card(i,'Reservekeeper' if pool[i]['position']==1 else f'Bænk {lineup["bench"].index(i)}') for i in lineup['bench'])
        html+='<div class="lab-bench"><div class="lab-bench-title">BÆNK · PRIORITERET RÆKKEFØLGE</div><div class="lab-row">'+bench+'</div></div>'
    return html


def show_lineup_pitch(lookup,lineup):
    ids=lineup['starters']+lineup['bench']
    st.html(pitch_html([dict(id=i,name=lookup[i]['name'],position=lookup[i]['position'],
        detail=f'£{lookup[i]["price"]/10:.1f}m · {len(lookup[i]["fixture_ids"])} kamp(e)',
        xp=lookup[i]['xp'],minutes=lookup[i]['expected_minutes']) for i in ids],lineup=lineup))
    st.caption('xP er spillerens egen prognose før anførerbonus. Minutter og point gælder hele GW’en.')


def transfer_card(title,outs,ins,bank,hits,gain):
    st.html(f'<div class="lab-transfer"><div class="lab-transfer-title">{_text(title)}</div>'
            f'<div class="lab-moves"><div><span class="lab-kicker lab-out">UD</span><br>{_text(outs)}</div>'
            f'<div><span class="lab-kicker lab-in">IND</span><br>{_text(ins)}</div></div>'
            f'<div class="lab-note">Bank £{bank/10:.1f}m · pointfradrag {hits} · simuleret gevinst over horisonten {gain:+.2f}</div></div>')


def summary_metrics(items):
    cells=''.join(f'<div class="lab-metric"><div class="lab-metric-label">{_text(label)}</div>'
                  f'<div class="lab-metric-value">{_text(value)}</div>'
                  f'<div class="lab-metric-note">{_text(note)}</div></div>' for label,value,note in items)
    st.html(f'<div class="lab-metrics" style="--count:{len(items)}">{cells}</div>')
