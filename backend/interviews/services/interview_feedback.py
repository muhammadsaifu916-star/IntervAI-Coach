"""Role- and score-aware interview improvement plans and recommendations."""

from __future__ import annotations

from .role_interview_constants import ROLE_INTERVIEW_SKILLS, experience_band_from_years

# Aligned with ResumeUpload.tsx tiers and interview question bands.
RESUME_TIER_LABELS = {
    'fresher': 'entry-level (0–1 years)',
    'junior_professional': 'mid-level (1–3 years)',
    'mid_level_expert': 'senior-level (3+ years)',
    'senior_professional': 'senior professional',
    'industry_veteran': 'industry veteran',
}

ROLE_STUDY_FOCUS: dict[str, tuple[str, ...]] = {
    'Python Developer': (
        'Django ORM, migrations, and API design',
        'Python testing, logging, and error handling',
        'Celery/async tasks and production debugging',
    ),
    'React Developer': (
        'React state, hooks, and component composition',
        'performance (re-renders, memoization, code-splitting)',
        'accessibility and testing React UI',
    ),
    'Java Developer': (
        'OOP design, Spring Boot services, and JPA',
        'transactions, concurrency, and JVM troubleshooting',
        'REST APIs, validation, and integration tests',
    ),
    'SQL Developer': (
        'query tuning, indexes, and execution plans',
        'JOINs, window functions, and reporting queries',
        'migrations, backups, and transaction safety',
    ),
    'Data Scientist': (
        'model evaluation, class imbalance, and leakage',
        'feature engineering and experiment design',
        'communicating results and limitations to stakeholders',
    ),
    'DevOps Engineer': (
        'CI/CD pipelines, Docker, and Kubernetes rollouts',
        'observability, incident response, and rollbacks',
        'secrets, IAM, and infrastructure as code',
    ),
    'Full Stack Developer': (
        'end-to-end auth, API contracts, and CORS/cookies',
        'React + backend integration and debugging',
        'deployment, caching, and schema changes safely',
    ),
    'Backend Developer': (
        'REST design, idempotency, and rate limiting',
        'database modeling, migrations, and query performance',
        'logging, tracing, and production incident triage',
    ),
    'Frontend Developer': (
        'responsive layout, Core Web Vitals, and browser quirks',
        'React patterns, bundle size, and client routing',
        'accessibility and component testing',
    ),
    'Security Engineer': (
        'OWASP risks, auth hardening, and secrets rotation',
        'network segmentation and vulnerability prioritization',
        'incident triage and secure SDLC practices',
    ),
    'Machine Learning Engineer': (
        'model serving, latency, and training-serving skew',
        'feature stores, batch vs online inference',
        'monitoring drift and safe model rollbacks',
    ),
    'AI Engineer': (
        'RAG quality, prompt safety, and evaluation',
        'PII handling and LLM guardrails',
        'embedding pipelines and cost/latency trade-offs',
    ),
    'Cloud Engineer': (
        'multi-AZ design, IAM least privilege, and cost control',
        'managed services vs containers/serverless',
        'disaster recovery and failover testing',
    ),
    'QA Engineer': (
        'test strategy, regression suites, and flaky test triage',
        'API/UI automation and risk-based testing',
        'bug reporting and release sign-off criteria',
    ),
    'Business Analyst': (
        'acceptance criteria, user stories, and UAT planning',
        'requirements workshops and scope negotiation',
        'metrics validation with business stakeholders',
    ),
    'Database Administrator': (
        'backup/restore, replication lag, and index maintenance',
        'capacity planning and major version upgrades',
        'security patching without downtime',
    ),
    'Mobile App Developer': (
        'offline sync, app performance, and OS-specific crashes',
        'secure storage and release/rollback on stores',
        'mobile UX patterns and API integration',
    ),
    'Blockchain Developer': (
        'smart contract safety, gas optimization, and testing',
        'mainnet vs testnet debugging and upgrade patterns',
        'wallet flows and transaction failure analysis',
    ),
    'Cybersecurity Analyst': (
        'SIEM triage, phishing response, and lateral movement',
        'patch compliance and tabletop exercises',
        'documenting findings for technical and business audiences',
    ),
    'UI/UX  Developer': (
        'usability testing, design systems, and handoff specs',
        'accessibility before release and UX metrics',
        'collaboration with engineering on feasible designs',
    ),
    'Software Developer': (
        'clean code, debugging, and unit/integration testing',
        'requirements breakdown and code review habits',
        'data structures applied to real product problems',
    ),
}

VIOLATION_ACTIONS = {
    'tab_switches': 'Stay on the interview tab for the full session — close notes, chat, and other tabs before you start.',
    'window_blur_events': 'Keep the interview window focused; turn off notifications and avoid switching apps mid-answer.',
    'screenshot_attempted': 'Do not capture screenshots during the interview — it is treated as an integrity violation.',
    'device_detected': 'Use a single camera/mic setup only; disconnect extra monitors or capture devices before starting.',
    'gaze_off_over_20s': 'Practice answering while looking at the camera; keep your face centered and visible.',
    'english_only_violation': 'Answer entirely in English for both technical and behavioral questions.',
    'camera_available': 'Fix camera permissions and lighting, then confirm your preview before starting.',
    'mic_available': 'Fix microphone permissions and record a 30-second test answer before your next attempt.',
}


def score_status(score: float | int) -> str:
    score = float(score or 0)
    if score < 45:
        return 'critical'
    if score < 60:
        return 'weak'
    if score < 70:
        return 'borderline'
    if score >= 80:
        return 'strong'
    return 'acceptable'


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item or '').strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def candidate_job_role(result: dict) -> str:
    from .interview_ai.engine import normalize_role

    raw_role = result.get('job_role') or result.get('target_role') or 'Software Developer'
    if raw_role == 'the target role':
        return raw_role
    return normalize_role(raw_role)


def candidate_primary_skill(result: dict) -> str:
    from .interview_ai.engine import normalize_skill

    role = candidate_job_role(result)
    role_skills = ROLE_INTERVIEW_SKILLS.get(role, [])
    if role_skills:
        return normalize_skill(role_skills[0])
    return normalize_skill(
        result.get('technical_skill_area') or result.get('target_skill_area') or 'Software Engineering'
    )


def candidate_experience_band(result: dict) -> str:
    band = str(result.get('experience_band') or '').strip()
    if band:
        return band
    years = result.get('experience_years')
    if years is None:
        years = result.get('years_experience')
    if years is not None:
        return experience_band_from_years(years)
    return 'fresher'


def _role_focus_phrases(role: str) -> list[str]:
    from .interview_ai.engine import normalize_skill

    if role in ROLE_STUDY_FOCUS:
        return list(ROLE_STUDY_FOCUS[role])
    skills = ROLE_INTERVIEW_SKILLS.get(role, ['Software Engineering'])
    return [f'{normalize_skill(skill)} concepts with real project examples' for skill in skills[:3]]


def _band_phrase(result: dict) -> str:
    """Human label matching resume upload tiers and interview difficulty band."""
    years = result.get('experience_years')
    if years is None:
        years = result.get('years_experience')
    if years is not None:
        y = float(years)
        if y <= 1:
            return RESUME_TIER_LABELS['fresher']
        if y <= 3:
            return RESUME_TIER_LABELS['junior_professional']
        if y < 6:
            return RESUME_TIER_LABELS['mid_level_expert']
    band = candidate_experience_band(result)
    return RESUME_TIER_LABELS.get(band, band.replace('_', ' '))


def _points_to_pass(final_score: float) -> float:
    return max(0.0, 70.0 - float(final_score or 0))


def _violation_recommendations(result: dict) -> list[str]:
    recommendations: list[str] = []
    for field, action in VIOLATION_ACTIONS.items():
        if field in {'camera_available', 'mic_available'}:
            if int(result.get(field, 1)) != 1:
                recommendations.append(action)
        elif int(result.get(field, 0) or 0) > 0:
            recommendations.append(action)
    if not recommendations and result.get('hard_fail_triggered'):
        reason = str(result.get('fail_reason') or '').strip()
        if reason:
            recommendations.append(f'Address this before retrying: {reason}')
    return recommendations


def _technical_recommendation(role: str, skill: str, score: float, status: str, focus: list[str]) -> str:
    topics = ', '.join(focus[:2])
    if status == 'critical':
        return (
            f'Technical score {score:.0f}/100 — rebuild core {skill} knowledge for a {role} role. '
            f'Study {topics}, then practice 5 role-specific questions daily using: concept → example → trade-off.'
        )
    if status == 'weak':
        return (
            f'Technical score {score:.0f}/100 — deepen {skill} answers with a real scenario, '
            f'two concrete steps you took, and one limitation or alternative you considered.'
        )
    if status == 'borderline':
        return (
            f'Technical score {score:.0f}/100 — you are close. For each {skill} answer, add one metric, '
            f'one trade-off, and one sentence on how you validated the approach.'
        )
    return (
        f'Strong technical performance ({score:.0f}/100). Keep rehearsing {role} scenarios on {topics} '
        f'to stay sharp for live interviews.'
    )


def _personality_recommendation(role: str, trait: str, score: float, status: str) -> str:
    if status in {'critical', 'weak'}:
        return (
            f'Behavioral score {score:.0f}/100 — prepare 5 STAR stories as a {role} covering conflict, failure, '
            f'deadline pressure, teamwork, and learning. Name situation, your action, and measurable outcome.'
        )
    if status == 'borderline':
        return (
            f'Behavioral score {score:.0f}/100 — extend each story with what you learned and how it changed '
            f'your approach on later {role} projects.'
        )
    return (
        f'Solid behavioral answers ({score:.0f}/100). Keep refining {trait.lower()} examples with clear results.'
    )


def build_recommendations(result: dict, weak_details: list[dict]) -> list[str]:
    recommendations: list[str] = []
    role = candidate_job_role(result)
    skill = candidate_primary_skill(result)
    trait = str(result.get('personality_trait') or 'Communication')
    focus = _role_focus_phrases(role)
    passed = result.get('final_decision', result.get('decision')) == 'pass'

    recommendations.extend(_violation_recommendations(result))

    weak_by_area = {item['area']: item for item in weak_details}
    metric_scores = {
        'Technical performance': float(result.get('technical_score', 0) or 0),
        'Personality performance': float(result.get('personality_score', 0) or 0),
        'Communication': float(result.get('communication_score', 0) or 0),
        'Attentiveness': float(result.get('attentiveness_score', 0) or 0),
        'Eye contact': float(result.get('eye_contact_score', 0) or 0),
        'Confidence': float(result.get('confidence_score', 0) or 0),
    }

    if 'Technical performance' in weak_by_area or (passed and metric_scores['Technical performance'] >= 80):
        item = weak_by_area.get('Technical performance') or {
            'score': metric_scores['Technical performance'],
            'status': score_status(metric_scores['Technical performance']),
        }
        recommendations.append(
            _technical_recommendation(role, skill, float(item['score']), item['status'], focus)
        )

    if 'Personality performance' in weak_by_area or (passed and metric_scores['Personality performance'] >= 80):
        item = weak_by_area.get('Personality performance') or {
            'score': metric_scores['Personality performance'],
            'status': score_status(metric_scores['Personality performance']),
        }
        recommendations.append(
            _personality_recommendation(role, trait, float(item['score']), item['status'])
        )

    for item in weak_details:
        area = item['area']
        score = float(item['score'])
        status = item['status']
        if area in {'Technical performance', 'Personality performance'}:
            continue
        if area == 'Communication':
            recommendations.append(
                f'Communication {score:.0f}/100 — open with a direct answer, add one supporting reason, '
                f'then a short {role} example; aim for 45–90 seconds per response.'
            )
        elif area == 'Confidence':
            recommendations.append(
                f'Confidence {score:.0f}/100 — rehearse aloud daily: state your headline answer first, '
                f'pause briefly instead of filling silence, and end with a clear conclusion.'
            )
        elif area == 'Attentiveness':
            recommendations.append(
                f'Attentiveness {score:.0f}/100 — use a quiet room, silence phone notifications, '
                f'and keep eyes toward the camera while listening and answering.'
            )
        elif area == 'Eye contact':
            recommendations.append(
                f'Eye contact {score:.0f}/100 — place the camera at eye level and practice '
                f'referring to notes without looking away for long stretches.'
            )
        elif area == 'Verbal fluency':
            filler = float(result.get('filler_ratio', 0) or 0)
            recommendations.append(
                f'Verbal fluency — filler ratio {filler:.0%}. Slow down slightly, pause instead of "um/uh", '
                f'and outline answers in three bullet points before you speak.'
            )
        elif area == 'Answer timing':
            recommendations.append(
                f'Answer timing — average {score:.0f}s per response. Target 45–90 seconds: '
                f'context, your actions, and result — trim tangents.'
            )

    if passed and not recommendations:
        recommendations.append(
            f'You passed as a {role}. Schedule one mock interview per week on {focus[0]} '
            f'to maintain readiness.'
        )
    elif not passed and not recommendations:
        gap = _points_to_pass(float(result.get('final_score', 0) or 0))
        recommendations.append(
            f'You need roughly {gap:.0f} more points to pass. Complete two full mock {role} interviews, '
            f'review transcripts, and rewrite your weakest answers using the STAR or concept–example–trade-off format.'
        )

    return _unique_keep_order(recommendations)[:8]


def build_overall_summary(result: dict, weak_details: list[dict], strong_points: list[str]) -> str:
    role = candidate_job_role(result)
    band = _band_phrase(result)
    final_score = float(result.get('final_score', 0) or 0)
    passed = result.get('final_decision', result.get('decision')) == 'pass'

    if passed:
        strengths = ', '.join(strong_points[:3]) if strong_points else 'consistent performance across metrics'
        return (
            f'You passed your {role} interview with {final_score:.0f}% ({band}). '
            f'Standout areas: {strengths}.'
        )

    gap = _points_to_pass(final_score)
    if weak_details:
        top = weak_details[0]
        focus_line = f'{top["area"]} ({top["score"]:.0f}/100, {top["status"]})'
        if len(weak_details) > 1:
            second = weak_details[1]
            focus_line += f' and {second["area"]} ({second["score"]:.0f}/100)'
    else:
        focus_line = 'overall answer quality and interview delivery'

    summary = (
        f'You scored {final_score:.0f}% on your {role} interview ({band}), below the 70% pass mark '
        f'by about {gap:.0f} points. Priority focus: {focus_line}.'
    )
    if result.get('hard_fail_triggered') and result.get('fail_reason'):
        summary += f' Note: {str(result["fail_reason"]).rstrip(".")}.'
    return summary


def generate_improvement_plan(result: dict, progress_report: dict | None = None) -> str:
    report = progress_report or generate_progress_report(result)
    passed = result.get('final_decision', result.get('decision')) == 'pass'
    role = candidate_job_role(result)
    skill = candidate_primary_skill(result)
    band = _band_phrase(result)
    final_score = float(result.get('final_score', 0) or 0)
    cooldown = int(result.get('cooldown_days', 0) or 0)
    weak_details = report.get('weak_details', [])
    recommendations = report.get('recommendations', [])
    focus = _role_focus_phrases(role)

    if passed:
        strengths = ', '.join(report.get('strong_points', [])[:3]) or 'consistent interview performance'
        return (
            f'You passed with {final_score:.0f}% as a {role} ({band}). '
            f'Strengths: {strengths}. '
            f'To stay ready: rehearse one {skill} question and one behavioral question daily, '
            f'and keep answers structured with examples from your own projects.'
        )

    sections: list[str] = [
        f'Interview result: {final_score:.0f}% as a {role} ({band}) — not yet at the 70% pass threshold.',
    ]

    if result.get('hard_fail_triggered'):
        sections.append(
            'First, fix the proctoring issue from this attempt before studying content — '
            'violations can override answer quality.'
        )

    if weak_details:
        priority = '; '.join(
            f'{item["area"]} ({item["score"]:.0f}/100, {item["status"]})'
            for item in weak_details[:3]
        )
        sections.append(f'This week, prioritize: {priority}.')
    else:
        sections.append('This week, prioritize structured answers and full mock interview runs.')

    plan_steps: list[str] = []
    weak_areas = {item['area'] for item in weak_details}

    if 'Technical performance' in weak_areas:
        plan_steps.append(
            f'Days 1–3: review {skill} fundamentals ({focus[0]}) and write bullet-point answers to 6 {role} technical questions'
        )
        plan_steps.append(
            f'Days 4–5: timed mock answers — each response must include concept, example, and trade-off'
        )
    if 'Personality performance' in weak_areas:
        plan_steps.append(
            'Draft 5 STAR behavioral stories (conflict, failure, deadline, teamwork, learning) and rehearse each in under 90 seconds'
        )
    if {'Communication', 'Confidence', 'Verbal fluency'} & weak_areas:
        plan_steps.append(
            'Record 3 answers daily; cut filler words and open with a one-sentence headline before details'
        )
    if {'Attentiveness', 'Eye contact'} & weak_areas or result.get('hard_fail_triggered'):
        plan_steps.append(
            'Run one full mock interview on camera in a quiet room with notifications disabled'
        )
    if not plan_steps:
        gap = _points_to_pass(final_score)
        plan_steps.append(
            f'Complete two timed mock interviews and rewrite answers until you consistently score above {min(70, final_score + gap + 5):.0f}%'
        )

    sections.append('Study plan: ' + '; '.join(plan_steps) + '.')

    if recommendations:
        sections.append('Next steps: ' + ' '.join(recommendations[:3]))

    if cooldown > 0:
        sections.append(f'Cooldown: {cooldown} day(s) before your next attempt — use this window for focused practice, not passive reading.')

    return ' '.join(sections)


def generate_progress_report(result: dict) -> dict:
    strong: list[str] = []
    weak_details: list[dict] = []
    score_details: list[dict] = []
    failed = result.get('final_decision', result.get('decision')) == 'fail'

    metric_map = {
        'Technical performance': result.get('technical_score', 0),
        'Personality performance': result.get('personality_score', 0),
        'Communication': result.get('communication_score', 0),
        'Attentiveness': result.get('attentiveness_score', 0),
        'Eye contact': result.get('eye_contact_score', 0),
        'Confidence': result.get('confidence_score', 0),
    }

    for area, raw_score in metric_map.items():
        score = float(raw_score or 0)
        status = score_status(score)
        detail = {'area': area, 'score': round(score, 2), 'status': status}
        score_details.append(detail)
        if status == 'strong':
            strong.append(area)
        if status in {'critical', 'weak'} or (failed and status == 'borderline'):
            weak_details.append(detail)

    filler_ratio = float(result.get('filler_ratio', 0) or 0)
    if filler_ratio > 0.18:
        weak_details.append({
            'area': 'Verbal fluency',
            'score': round((1 - filler_ratio) * 100, 2),
            'status': 'critical' if filler_ratio > 0.28 else 'weak',
        })

    if result.get('avg_answer_seconds_source') == 'provided':
        avg_answer_seconds = float(result.get('avg_answer_seconds', 60) or 60)
        if avg_answer_seconds < 20 or avg_answer_seconds > 150:
            weak_details.append({
                'area': 'Answer timing',
                'score': round(avg_answer_seconds, 2),
                'status': 'weak',
            })

    priority = {'critical': 0, 'weak': 1, 'borderline': 2, 'acceptable': 3, 'strong': 4}
    weak_details = sorted(weak_details, key=lambda x: (priority.get(x['status'], 9), x['score']))
    score_order = {
        'Technical performance': 0,
        'Personality performance': 1,
        'Communication': 2,
        'Confidence': 3,
        'Attentiveness': 4,
        'Eye contact': 5,
    }
    score_details = sorted(score_details, key=lambda x: score_order.get(x['area'], 99))
    weak_points = [item['area'] for item in weak_details]
    recommendations = build_recommendations(result, weak_details)

    return {
        'overall_summary': build_overall_summary(result, weak_details, strong),
        'strong_points': sorted(set(strong)) or ['Consistent participation'],
        'weak_points': _unique_keep_order(weak_points),
        'weak_details': weak_details,
        'score_details': score_details,
        'recommendations': recommendations,
        'cooldown_days': int(result.get('cooldown_days', 0) or 0),
    }
