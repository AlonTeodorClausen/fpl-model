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
_READINESS_MESSAGES = {
    'no_future_deadline': 'Ingen kommende officiel deadline i datagrundlaget',
    'source_after_check_time': 'En datakilde ligger efter kontrollens tidspunkt',
    'identity_conflict': 'Konflikt i spiller- eller kampidentitet',
    'history_refresh_required': 'Hent opdateret kampvis spillerhistorik',
    'missing_player_histories': 'Nogle spillerhistorikker mangler',
    'quarantined_player_rows': 'Nogle historikrækker kræver kontrol',
    'fixtures_in_progress': 'Kampe er stadig i gang',
    'context_stale': 'Opdatér spillerpriser og kampplan',
    'odds_coverage_unresolved': 'Odds-dækning kan ikke fastslås',
    'odds_fallback': 'Nogle kampe bruger prognosen uden odds',
}
_QUARANTINE_MESSAGES = {
    'fixture_not_started': 'Kampens officielle status er ikke afklaret',
    'unknown_player_id': 'Ukendt spiller-ID',
    'unknown_fixture_team_id': 'Ukendt hold-ID for kampen',
    'duplicate_player_fixture': 'Flere rækker for samme spiller og kamp',
}


def readiness_message(reasons):
    return ' · '.join(_READINESS_MESSAGES.get(reason, 'Datagrundlaget kræver kontrol')
                    for reason in reasons)


def quarantine_reason_label(reason):
    return _QUARANTINE_MESSAGES.get(reason,'Anden valideringsårsag')


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


def _positive_code(value):
    """Only FPL's numeric codes may be interpolated into official image URLs."""
    digits = str(value)
    if isinstance(value, bool) or not digits.isascii() or not digits.isdecimal():
        return None
    code = int(digits)
    return code if code > 0 else None


def official_media(players, teams):
    """Display-only image references from the captured FPL bootstrap identities."""
    clubs = {team['id']: team for team in teams}
    result = {}
    for player in players:
        club = clubs.get(player.get('team'), {})
        result[player['id']] = dict(
            photo_code=_positive_code(player.get('code')),
            club_code=_positive_code(club.get('code')),
            club_short=club.get('short_name', ''),
        )
    return result


def _image_url(kind, code):
    code = _positive_code(code)
    if code is None:
        return None
    if kind == 'player':
        # The current Premier League player profiles use this season's portraits.
        return f'https://resources.premierleague.com/premierleague25/photos/players/110x140/{code}.png'
    return f'https://resources.premierleague.com/premierleague/badges/70/t{code}.png'


def _media_html(player, *, pitch=False):
    """CSS backgrounds leave initials/club abbreviations visible on image failure."""
    photo = _image_url('player', player.get('photo_code'))
    club = _image_url('club', player.get('club_code'))
    initial = _text(str(player['name'])[:1].upper())
    club_short = _text(str(player.get('club_short') or '')[:5])
    avatar_class = 'lab-pitch-avatar' if pitch else 'lab-list-avatar'
    photo_style = f' style="background-image:url(\'{photo}\')"' if photo else ''
    club_style = f' style="background-image:url(\'{club}\')"' if club else ''
    avatar = (f'<span class="{avatar_class}" role="img" aria-label="Spillerfoto: {_text(player["name"])}"'
              f'{photo_style}><span class="lab-avatar-initial">{initial}</span></span>')
    badge = (f'<span class="lab-club-mark" role="img" aria-label="Klub: {club_short}"'
             f'{club_style}><span>{club_short}</span></span>') if club_short else ''
    return avatar + badge


def apply_theme():
    stylesheet = Path(__file__).with_name('theme.css').read_text(encoding='utf-8')
    st.html('<style>' + stylesheet + '</style>')


def _player_link(player, clickable):
    pid = player['id']
    if not clickable or type(pid) is not int or pid <= 0:
        return None
    return f'href="?player_id={pid}" aria-label="Se prognose for {_text(player["name"])}"'


def pitch_html(players, *, lineup=None, clickable=False):
    """Players use display fields; absence of lineup means positional squad, never XI."""
    pool={p['id']:p for p in players}
    def card(pid,role=''):
        p=pool[pid];badge=''
        if lineup and pid==lineup['captain']:badge=' <span class="lab-badge">C</span>'
        elif lineup and pid==lineup.get('vice_captain'):badge=' <span class="lab-badge">V</span>'
        warning=f' <span class="lab-doubt">{_text(p["flag"])}</span>' if p.get('flag') else ''
        stat=f'<div class="lab-stat">{p["xp"]:.2f} xP · {p["minutes"]:.0f} min</div>' if p.get('xp') is not None and p.get('minutes') is not None else ''
        media=f'<div class="lab-pitch-media">{_media_html(p,pitch=True)}</div>'
        link = _player_link(p, clickable)
        tag = 'a' if link else 'div'
        attrs = f' {link}' if link else ''
        css = ' lab-player-link' if link else ''
        return f'<{tag} class="lab-player{css}"{attrs}>{media}<div class="lab-player-body"><div class="lab-name">{_text(p["name"])}{badge}{warning}</div><div class="lab-meta">{_text(p.get("detail",""))}</div>{stat}<div class="lab-meta">{_text(role)}</div></div></{tag}>'
    ids=lineup['starters'] if lineup else list(pool)
    rows=['<div class="lab-row">'+''.join(card(i) for i in ids if pool[i]['position']==pos)+'</div>' for pos in range(1,5)]
    html='<div class="lab-pitch-scroll"><div class="lab-pitch" role="group" aria-label="'+('Startellever' if lineup else 'Trup efter position, ikke en startellever')+'">'+''.join(rows)+'</div></div>'
    if lineup:
        bench=''.join(card(i,'Reservekeeper' if pool[i]['position']==1 else f'Bænk {lineup["bench"].index(i)}') for i in lineup['bench'])
        html+='<div class="lab-bench"><div class="lab-bench-title">BÆNK · PRIORITERET RÆKKEFØLGE</div><div class="lab-row">'+bench+'</div></div>'
    return html


def list_html(players, *, lineup=None, clickable=False):
    """Readable squad/lineup alternative; an absent row is never inferred as DNP."""
    pool = {p['id']: p for p in players}
    positions = {1: 'Målmænd', 2: 'Forsvarere', 3: 'Midtbanespillere', 4: 'Angribere'}

    def row(pid, role=''):
        p = pool[pid]
        badges = []
        if lineup and pid == lineup['captain']:
            badges.append('Anfører')
        elif lineup and pid == lineup.get('vice_captain'):
            badges.append('Viceanfører')
        if p.get('flag'):
            badges.append(str(p['flag']))
        badge_html = ''.join(f'<span class="lab-list-badge">{_text(b)}</span>' for b in badges)
        stat = (f'<span class="lab-list-stat">{p["xp"]:.2f} xP'
                f'<small>{p["minutes"]:.0f} min</small></span>'
                if p.get('xp') is not None and p.get('minutes') is not None else '')
        detail = _text(p.get('detail', ''))
        link = _player_link(p, clickable)
        tag = 'a' if link else 'div'
        attrs = f' {link}' if link else ''
        css = ' lab-player-link' if link else ''
        return (f'<{tag} class="lab-list-row{css}"{attrs}>{_media_html(p)}<div class="lab-list-person">'
                f'<strong>{_text(p["name"])}</strong>{badge_html}'
                f'<small>{detail}{" · " + _text(role) if role else ""}</small></div>{stat}</{tag}>')

    def section(title, ids):
        return (f'<section class="lab-list-section"><h4>{_text(title)}</h4>'
                + ''.join(row(pid) for pid in ids) + '</section>')

    ids = lineup['starters'] if lineup else list(pool)
    main = ''.join(section(positions[pos], [i for i in ids if pool[i]['position'] == pos])
                   for pos in positions if any(pool[i]['position'] == pos for i in ids))
    if lineup:
        bench = ''.join(row(pid, 'Reservekeeper' if pool[pid]['position'] == 1
                            else f'Bænk {index}') for index, pid in enumerate(lineup['bench']))
        main += f'<section class="lab-list-section"><h4>Bænk · rækkefølge</h4>{bench}</section>'
    label = 'Startellever og bænk' if lineup else 'Trup efter position, ikke en startellever'
    return f'<div class="lab-list" role="group" aria-label="{label}">{main}</div>'


def team_html(players, *, lineup=None, view='Liste', clickable=False):
    """The same forecast fields in either a compact list or a pitch."""
    if view == 'Liste':
        return list_html(players, lineup=lineup, clickable=clickable)
    if view == 'Bane':
        return pitch_html(players, lineup=lineup, clickable=clickable)
    raise ValueError('Ukendt holdvisning')


def decision_card_html(decision, *, event, names, stale=False, chip=None, data_attention=False):
    """A concise entry point derived only from an existing comparison report."""
    if decision['count']:
        heading = f'{decision["count"]} transfer' + ('s' if decision['count'] != 1 else '') + ' nu'
        action = (f'{_text(names(decision["out"]))}<span class="lab-decision-arrow">→</span>'
                  f'{_text(names(decision["in"]))}')
        if chip:
            action += f' · {_text(chip)}'
    else:
        heading = f'Behold truppen · {_text(chip)}' if chip else 'Behold holdet denne uge'
        action = 'Ingen transfers før den næste deadline.'
    kicker = 'GEMT FORSLAG' if stale else 'DATA SKAL KONTROLLERES' if data_attention else 'NÆSTE TRÆK'
    stale_note = (' Indstillinger eller hold er ændret. Genberegn før du handler.' if stale else '')
    data_note = (' Opdatér data og genberegn, før du følger forslaget.' if data_attention else '')
    css = 'lab-decision lab-decision-stale' if stale or data_attention else 'lab-decision'
    return (f'<section class="{css}" aria-label="Anbefaling for GW{int(event)}">'
            f'<div class="lab-decision-kicker">{kicker} · GW{int(event)}</div>'
            f'<h2>{heading}</h2><p class="lab-decision-action">{action}</p>'
            f'<div class="lab-decision-stats">'
            f'<div><small>Næste GW</small><strong>{decision["next_gw_gain"]:+.2f} point</strong></div>'
            f'<div><small>Hele horisonten</small><strong>{decision["horizon_gain"]:+.2f} point</strong></div>'
            f'<div><small>Bank efter</small><strong>£{decision["bank_after"]/10:.1f}m</strong></div>'
            f'<div><small>Fradrag</small><strong>{decision["hits"]} pointfradrag</strong></div>'
            f'</div><p class="lab-decision-foot">Simulerede holdpoint sammenlignet med dit uændrede hold under de samme prognoser. '
            f'Små forskelle kan være simulationsstøj.{stale_note}{data_note}</p></section>')


def next_step_card_html(*, player_count, profile_error, readiness_status='ready',
                        price_estimates=False, can_refresh=False):
    """Explain the next action without implying that an incomplete team is ready."""
    attention = False
    if player_count < 15:
        heading = 'Hent dit hold fra FPL'
        detail = 'Indtast dit hold-ID nedenfor, eller vælg dine spillere manuelt.'
    elif profile_error:
        heading = 'Færdiggør dit hold'
        detail = 'Tjek bank, gratis transfers, spillere og salgsværdier under “Redigér bank og transfers”, og gem holdet.'
    elif readiness_status == 'blocked':
        heading = 'Nye forslag er blokeret'
        detail = 'Datagrundlaget mangler nødvendige oplysninger. Se advarslen nedenfor.'
        attention = True
    elif readiness_status == 'limited':
        heading = 'Kun foreløbig beregning'
        detail = 'Opdatér data, eller vælg udtrykkeligt at beregne med ufuldstændig historik.'
        attention = True
    elif readiness_status == 'attention':
        heading = 'Opdatér data før du vælger'
        detail = ('Brug “Hent seneste data” nedenfor, og kontrollér holdet bagefter.' if can_refresh else
                  'Datagrundlaget kræver kontrol, før du følger et forslag.')
        attention = True
    elif price_estimates:
        heading = 'Kontrollér salgsværdier'
        detail = 'Nogle priser er estimater. Ret dem under “Redigér bank og transfers”, før du følger et forslag.'
        attention = True
    else:
        heading = 'Klar til forslag'
        detail = 'Vælg antal runder nedenfor. Vi sammenligner at beholde holdet med transfermuligheder.'
    css = 'lab-decision lab-decision-attention' if attention else 'lab-decision lab-decision-empty'
    return (f'<section class="{css}">'
            '<div class="lab-decision-kicker">NÆSTE SKRIDT</div>'
            f'<h2>{heading}</h2><p>{detail}</p></section>')


def decision_overview_html(decision, *, event, names, alternatives, weeks,
                           stale=False, chip=None, data_attention=False):
    """A report-backed summary; every number comes from the selected plan."""
    card = decision_card_html(decision, event=event, names=names, stale=stale, chip=chip,
                              data_attention=data_attention)
    other_rows = ''.join(
        f'<div class="lab-alternative"><strong>{_text(p["label"])}</strong>'
        f'<span>{p["next_gw_gain"]:+.2f} nu · {p["total_gain"]:+.2f} over horisonten'
        f'{" · " + str(p["hits"]) + " pointfradrag" if p.get("hits") else ""}</span></div>'
        for p in alternatives[:3])
    if not other_rows:
        other_rows = '<p class="lab-note">Ingen andre forskellige forslag i denne beregning.</p>'
    alternative_panel = ('<aside class="lab-alternatives"><div class="lab-panel-kicker">ANDRE VALG</div>'
                         '<p>Samme prognoser og begrænsninger</p>' + other_rows + '</aside>')
    week_cards = ''.join(
        f'<div class="lab-outlook-week"><span>GW{int(w["event"])}</span>'
        f'<strong>{w["mean"]:.1f} point</strong>'
        f'<small>{w["gain"]:+.2f} mod behold</small></div>' for w in weeks)
    outlook = ('<section class="lab-outlook"><div class="lab-panel-kicker">PLANEN UGE FOR UGE</div>'
               '<div class="lab-outlook-weeks">' + week_cards + '</div></section>')
    return '<div class="lab-overview"><div class="lab-overview-top">' + card + alternative_panel + '</div>' + outlook + '</div>'


def show_lineup(lookup, lineup, *, view='Liste', media_by_id=None):
    ids = lineup['starters'] + lineup['bench']
    players = [dict(id=i, name=lookup[i]['name'], position=lookup[i]['position'],
                    detail=f'£{lookup[i]["price"]/10:.1f}m · {len(lookup[i]["fixture_ids"])} kamp(e)',
                    xp=lookup[i]['xp'], minutes=lookup[i]['expected_minutes'],
                    **((media_by_id or {}).get(i) or {})) for i in ids]
    st.html(team_html(players, lineup=lineup, view=view))
    if view == 'Bane':
        st.caption('Skub banen vandret på en smal skærm for at se alle spillere.')
    st.caption('xP er spillerens egen prognose før anførerbonus. Minutter og point gælder hele GW’en.')


def show_lineup_pitch(lookup,lineup):
    show_lineup(lookup, lineup, view='Bane')


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
