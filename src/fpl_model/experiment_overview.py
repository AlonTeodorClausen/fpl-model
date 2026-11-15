"""One status table for every model experiment; mirrors notes/experiments.md."""

STATUS_ORDER = ['Standard', 'Tilvalg', 'Afprøves', 'Pensioneret']

EXPERIMENTS = [
    dict(name='Standardmodel', version='component_baseline_v1', status='Standard',
         changes='Hele prognosen: spilletid, mål, assists, clean sheets, bonus og øvrige hændelser.',
         result='Reference for alle andre forsøg. Bedre point-MAE end det simple gennemsnit i GW8–10, '
                'men dårligere minut-MAE for faste spillere.',
         note=None),
    dict(name='Odds til angreb og forsvar', version='component_attacking_odds_v1', status='Tilvalg',
         changes='Mål, assists og clean sheets fordeles ud fra bookmakerodds, hvor der er gemte odds.',
         result='Endnu ikke efterkontrolleret på endelige udfald. Kræver manuelt hentede odds.',
         note='attacking_odds.md'),
    dict(name='Minutmodel v2', version='component_minutes_v2', status='Afprøves',
         changes='Kun spilletid: startchance, indhop når spilleren ikke starter og minutter givet rolle '
                 'estimeres hver for sig, nyere kampe vægter mest, hele kampe trækkes for sig.',
         result='Fastlagt 15. november før evaluering. Afprøves prospektivt på GW12–15.',
         note='minutes_v2.md'),
    dict(name='Defensiv oddsvariant', version='component_defensive_odds_v1', status='Pensioneret',
         changes='Kun clean sheets og indkasserede mål fra odds.',
         result='0 af 10 kampe fik odds i testen, så der er intet resultat. Dækket af oddsmodellen for '
                'angreb og forsvar.',
         note='defensive_odds.md'),
    dict(name='Rolle, returminutter og fælles mål', version='component_shared_goals_v1', status='Pensioneret',
         changes='Nyere start/indhop-historik, manuelle returantagelser og fælles mål for holdet.',
         result='Samlet minut-MAE 18,22 → 17,57, men faste spillere blev dårligere: 21,46 → 22,92. '
                'Afløses af minutmodel v2.',
         note='model_evolution.md'),
    dict(name='Rollespecifik spilletid', version='component_role_transitions_v2', status='Pensioneret',
         changes='Spilletid ud fra rolle (starter, rotation, indskifter, reserve) lært af tidligere kampe.',
         result='Bedre for startere og reserver, men det simple gennemsnit var stadig bedre samlet. '
                'Afløses af minutmodel v2.',
         note='role_minutes.md'),
    dict(name='Frekvensprior 0,25 og 0,10', version='component_frequency_025_v1', status='Pensioneret',
         changes='Svagere udglatning af start/indhop/ingen spilletid.',
         result='Færre minutfejl, men dårligere point-CRPS for faste spillere (0,019–0,027 over seeds).',
         note='frequency_prior_experiment.md'),
    dict(name='Dødboldsroller', version='set_piece_roles', status='Pensioneret',
         changes='Flytter en antaget del af mål og assists til straffe-, frispark- og hjørnesparkstagere.',
         result='Vægtene er antagelser uden data at kalibrere mod. Ingen evaluering mulig.',
         note='set_piece_roles.md'),
    dict(name='Præstationsafhængig bonus', version='conditional_bonus_v1', status='Pensioneret',
         changes='Kun bonus: lært af tidligere kampe og simulerede præstationer.',
         result='Små, blandede forskelle. Point-MAE for faste spillere 2,5442 → 2,5463.',
         note='conditional_bonus.md'),
    dict(name='Sidste sæsons xG/xA som prior', version='previous_season_attack_prior_v1', status='Pensioneret',
         changes='Kun xG/xA-udgangspunktet for spillere.',
         result='Små, blandede forskelle. Point-MAE for faste spillere 2,5442 → 2,5354, RMSE lidt højere.',
         note='previous_season_priors.md'),
    dict(name='FPL-assistkorrektion', version='fpl_assist_correction_v1', status='Pensioneret',
         changes='Én fælles faktor mellem xA og FPL-assists.',
         result='Dårligere: point-MAE for faste spillere 2,5442 → 2,5665.',
         note='fpl_assist_correction.md'),
]


def overview_rows():
    order = {s: i for i, s in enumerate(STATUS_ORDER)}
    return sorted(EXPERIMENTS, key=lambda r: order[r['status']])
