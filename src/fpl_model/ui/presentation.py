"""Display-only components. Never select players, infer a lineup or compute forecasts."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import streamlit as st

from fpl_model.label_contracts import utc


_MONTHS = ('januar', 'februar', 'marts', 'april', 'maj', 'juni',
           'juli', 'august', 'september', 'oktober', 'november', 'december')


def friendly_time(value):
    """Show observed times in the user's Danish timezone, never as raw ISO text."""
    local = utc(value).astimezone(ZoneInfo('Europe/Copenhagen'))
    return f'{local.day}. {_MONTHS[local.month - 1]} kl. {local:%H.%M}'


def snapshot_option(path):
    """Name a local version by capture time without exposing its raw run ID."""
    path = Path(path)
    try:
        manifest = json.loads((path / 'manifest.json').read_text())
        observed = manifest.get('completed_at') or manifest.get('created_at')
        if observed:
            return friendly_time(observed)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        observed = datetime.strptime(path.name[:24], '%Y-%m-%d_%H%M%S%fZ').replace(tzinfo=timezone.utc)
        return friendly_time(observed)
    except ValueError:
        return 'Dato ukendt'


def saved_comparison_option(path):
    """Display a saved local report without exposing its artifact directory ID."""
    try:
        observed = datetime.strptime(Path(path).parent.name[:22], '%Y%m%dT%H%M%S%fZ')
        return 'Beregnet ' + friendly_time(observed.replace(tzinfo=timezone.utc))
    except ValueError:
        return 'Gemt forslag (dato ukendt)'


def _text(value):
    return escape(str(value), quote=True)


def apply_theme():
    st.html('''<style>
    :root { --ink:#17302f; --muted:#667773; --accent:#0a7862; --line:#dbe5df; }
    [data-testid="stAppViewContainer"] { background:linear-gradient(145deg,#f8faf8 0%,#eef4f1 100%); color:var(--ink); }
    [data-testid="stHeader"] { background:rgba(248,250,248,.92); }
    .block-container { max-width:1120px; padding-top:2.1rem; padding-bottom:4rem; }
    h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; }
    h1 { font-size:2.65rem !important; font-weight:800 !important; margin-bottom:.6rem !important; }
    h3 { font-weight:750 !important; margin-top:1.1rem !important; }
    [data-testid="stSidebar"] { background:#18312f; }
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h2 { color:#edf5f8; }
    [data-testid="stSidebar"] [role="combobox"] { color:#142c40; }
    [data-testid="stExpander"] { background:#fff; border:1px solid var(--line); border-radius:15px; box-shadow:0 2px 10px #1d433010; }
    [data-testid="stMetric"] { background:#fff; padding:16px; border:1px solid var(--line); border-radius:14px; }
    [data-testid="stMetricLabel"] { color:var(--muted); }
    [data-testid="stBaseButton-primary"] { background:#0a7862; border-color:#0a7862; border-radius:11px; font-weight:700; min-height:2.65rem; }
    [data-testid="stBaseButton-primary"]:hover { background:#075e4e; border-color:#075e4e; }
    [data-testid="stBaseButton-secondary"] { border-radius:10px; }
    .lab-metrics { display:grid; grid-template-columns:repeat(var(--count),minmax(0,1fr)); gap:12px; margin:10px 0 22px; }
    .lab-metric { background:white; border:1px solid var(--line); border-radius:14px; padding:17px 18px; box-shadow:0 3px 14px #1d433012; }
    .lab-metric-label { color:#617586; font-size:12px; }
    .lab-metric-value { font-size:28px; font-weight:780; color:var(--ink); letter-spacing:-1px; margin-top:4px; }
    .lab-metric-note { font-size:11px; color:#617586; margin-top:3px; }
    .lab-brand { color:#f4fbff; font-size:24px; font-weight:800; letter-spacing:-1px; padding:12px 0 2px; }
    .lab-brand span { color:#7bdac1; } .lab-kicker { color:#0a7862; font-size:11px; font-weight:800; letter-spacing:1.8px; text-transform:uppercase; }
    .lab-pitch { background:repeating-linear-gradient(0deg,#245d4d 0px,#245d4d 82px,#296653 82px,#296653 164px);
      border:1px solid #1f5848; border-radius:20px; padding:24px 14px; margin:8px 0 20px; position:relative; overflow:hidden; box-shadow:0 14px 32px #16473420; }
    .lab-pitch:before { content:""; position:absolute; inset:14px; border:1px solid #ffffff30; border-radius:3px; pointer-events:none; }
    .lab-pitch:after { content:""; position:absolute; width:90px; height:90px; border:1px solid #ffffff30;
      border-radius:50%; top:45%; left:calc(50% - 45px); pointer-events:none; }
    .lab-row { display:flex; justify-content:center; gap:10px; position:relative; z-index:1; margin:12px 0 20px; }
    .lab-player { width:132px; min-width:0; text-align:center; }
    .lab-shirt { width:35px; height:35px; margin:0 auto 4px; display:block; background:linear-gradient(90deg,#e2f3ed 40%,#67bba3 40%,#67bba3 60%,#e2f3ed 60%); clip-path:polygon(30% 10%,10% 23%,2% 50%,23% 58%,28% 45%,28% 94%,73% 94%,73% 45%,78% 58%,98% 50%,90% 23%,70% 10%,60% 18%,40% 18%); }
    .lab-player-body { background:#ffffff; border-radius:10px; padding:8px 4px; box-shadow:0 4px 12px #002d2830; }
    .lab-name { font-weight:750; color:#142c40; font-size:13px; overflow-wrap:anywhere; }
    .lab-meta { color:#617586; font-size:11px; margin-top:3px; }
    .lab-stat { color:#087f6f; font-size:12px; font-weight:750; margin-top:3px; }
    .lab-badge { display:inline-block; background:#142c40; color:white; border-radius:12px; padding:1px 5px; font-size:10px; }
    .lab-doubt { color:#895400; background:#fff2ce; border-radius:4px; padding:1px 4px; font-size:10px; }
    .lab-bench { background:#e6edf1; border-radius:12px; padding:8px 12px; margin-bottom:18px; }
    .lab-bench .lab-row { margin:8px 0; } .lab-bench-title { color:#526a7d; font-size:11px; font-weight:800; letter-spacing:1px; }
    .lab-transfer { border:1px solid var(--line); border-radius:16px; background:white; padding:20px; margin:8px 0 14px; box-shadow:0 4px 16px #1d433012; }
    .lab-transfer-title { font-size:18px; font-weight:750; color:#142c40; margin-bottom:10px; }
    .lab-moves { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
    .lab-out { color:#9b3b44; } .lab-in { color:#087f6f; }
    .lab-note { color:#617586; font-size:12px; margin-top:12px; }
    .lab-weeks { display:grid; gap:9px; margin:12px 0 18px; }
    .lab-week { display:flex; gap:15px; align-items:flex-start; background:#fff; border:1px solid var(--line); border-radius:13px; padding:13px 16px; }
    .lab-week-gw { flex:none; min-width:47px; color:#0a7862; font-size:13px; font-weight:800; }
    .lab-week-action { color:var(--ink); font-size:14px; font-weight:700; line-height:1.35; overflow-wrap:anywhere; }
    .lab-week-meta { color:var(--muted); font-size:12px; margin-top:4px; line-height:1.4; }
    .lab-arrow { color:#0a7862; padding:0 5px; }
    @media(max-width:640px) { .lab-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; } .lab-metric { padding:12px; } .block-container { padding:1.3rem .8rem; } h1 { font-size:2.2rem !important; }
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


def week_plan_html(steps, names, chip_labels):
    """Compact transfer timeline; detailed numeric tables remain available separately."""
    cards = []
    for step in steps:
        if step['out'] or step['in']:
            action = f'{_text(names(step["out"]))}<span class="lab-arrow">→</span>{_text(names(step["in"]))}'
        else:
            action = 'Behold holdet'
        chip = chip_labels.get(step.get('chip'))
        if chip:
            action += f' · {_text(chip)}'
        used = step['used']
        meta = (f'Bank £{step["bank_after"]/10:.1f}m · {used} gratis '
                f'{"transfer" if used == 1 else "transfers"} brugt · '
                f'{step["remaining"]} tilbage · {step["hits"]} pointfradrag')
        cards.append(f'<div class="lab-week"><span class="lab-week-gw">GW{step["event"]}</span>'
                     f'<div><div class="lab-week-action">{action}</div>'
                     f'<div class="lab-week-meta">{meta}</div></div></div>')
    return '<div class="lab-weeks">' + ''.join(cards) + '</div>'


def summary_metrics(items):
    cells=''.join(f'<div class="lab-metric"><div class="lab-metric-label">{_text(label)}</div>'
                  f'<div class="lab-metric-value">{_text(value)}</div>'
                  f'<div class="lab-metric-note">{_text(note)}</div></div>' for label,value,note in items)
    st.html(f'<div class="lab-metrics" style="--count:{len(items)}">{cells}</div>')
