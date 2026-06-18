import json

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from .models import InterviewSession, InterviewQuestion, InterviewAnswer
from .serializers import (
    InterviewQuestionSerializer,
    StartInterviewSerializer,
    SubmitInterviewSerializer,
    SubmitMonitoringSerializer,
    TranscribeAnswerSerializer,
)
from .services.interview_engine import prepare_interview_start, evaluate_session
from .services.interview_ai.engine import experience_band_from_years, normalize_role
from .services.question_selector import normalize_question_text
from .services.question_quality import normalize_for_dedupe
from .services.speech_to_text import transcribe_audio_file, transcribe_uploads
from .services.attentiveness_monitoring import (
    merge_monitoring_state,
    build_session_meta_from_monitoring,
)

# ── Constants ──────────────────────────────────────────────────────────────────
INTERVIEW_NUM_QUESTIONS        = 6
INTERVIEW_TIME_LIMIT_SECONDS   = 900   # 15 minutes
QUIZ_PASS_SCORE_REQUIRED       = 70
COOLDOWN_DAYS_EXPIRED          = 3


def _user_passed_quiz(user) -> bool:
    from quizzes.models import QuizSession
    return QuizSession.objects.filter(user=user, passed=True).exists()


def _latest_submitted_session(user):
    return (
        InterviewSession.objects
        .filter(user=user, submitted_at__isnull=False)
        .order_by('-submitted_at')
        .first()
    )


def _in_flight_session(user):
    return (
        InterviewSession.objects
        .filter(user=user, submitted_at__isnull=True)
        .order_by('-started_at')
        .first()
    )


def _resume_context(session):
    questions = InterviewQuestion.objects.filter(session=session).order_by('order')
    elapsed = int((timezone.now() - session.started_at).total_seconds())
    time_left = max(0, INTERVIEW_TIME_LIMIT_SECONDS - elapsed)
    return questions, time_left


def _build_ai_answers(questions, answers_map, job_role=''):
    payload = []
    for question in questions:
        payload.append({
            'question_type': question.question_type,
            'category': question.category,
            'question_text': question.question_text,
            'transcript': answers_map.get(str(question.id), ''),
            'reference_keywords': question.reference_keywords or '',
            'reference_points': question.reference_points or '',
            'job_role': job_role,
        })
    return payload


def _apply_analysis_to_session(session, analysis: dict, cooldown_until):
    session.technical_score = analysis.get('technical_score')
    session.personality_score = analysis.get('personality_score')
    session.attentiveness_score = analysis.get('attentiveness_score')
    session.eye_contact_score = analysis.get('eye_contact_score')
    session.communication_score = analysis.get('communication_score')
    session.grammar_score = None
    session.confidence_score = analysis.get('confidence_score')
    session.filler_ratio = analysis.get('filler_ratio')
    session.score = analysis.get('final_score', analysis.get('score'))
    session.passed = analysis.get('passed', analysis.get('decision') == 'pass')
    session.cooldown_until = cooldown_until
    session.improvement_plan = analysis.get('improvement_plan', '')
    session.progress_report = analysis.get('progress_report', {})
    session.analysis_data = {
        k: analysis.get(k)
        for k in [
            'decision', 'hard_fail_triggered', 'fail_reason', 'cooldown_days',
            'communication_score', 'confidence_score', 'filler_ratio',
            'avg_answer_length', 'avg_answer_seconds', 'avg_answer_seconds_source', 'per_question_scores',
            'full_report_text', 'target_role', 'target_skill_area',
            'technical_skill_area', 'personality_trait', 'experience_band',
            'experience_years', 'years_experience', 'job_role',
            'interview_expired', 'model_reference_score', 'focus_penalty_applied',
            'completion_ratio', 'questions_answered', 'questions_total', 'incomplete_penalty_applied',
        ]
        if analysis.get(k) is not None
    }


def _persist_answers(session, questions, answers_map, analysis):
    InterviewAnswer.objects.filter(session=session).delete()
    per_question = analysis.get('per_question_scores', [])
    for question in questions:
        transcript = answers_map.get(str(question.id), '')
        InterviewAnswer.objects.create(
            session=session,
            question=question,
            transcript=transcript,
            score=next(
                (
                    item.get('score')
                    for item in per_question
                    if item.get('question_text') == question.question_text
                ),
                None,
            ),
        )


def _cooldown_from_analysis(analysis):
    cooldown_days = int(analysis.get('cooldown_days', 0) or 0)
    if cooldown_days <= 0:
        return None
    return timezone.now() + timedelta(days=cooldown_days)


def _finalize_session(user, session, questions, answers_map, interview_expired=False):
    avg_answer_seconds = None
    timings = session.answer_timings or {}
    if timings:
        values = [float(v) for v in timings.values() if v is not None]
        if values:
            avg_answer_seconds = sum(values) / len(values)

    monitoring_meta = build_session_meta_from_monitoring(
        session.monitoring_data,
        avg_answer_seconds=avg_answer_seconds,
    )
    session_meta = {
        'job_role': session.job_role,
        'experience_years': session.years_experience,
        'experience_band': session.experience_band or experience_band_from_years(session.years_experience),
        **monitoring_meta,
    }

    analysis = evaluate_session(
        answers=_build_ai_answers(questions, answers_map, job_role=session.job_role),
        session_meta=session_meta,
        interview_expired=interview_expired,
    )
    cooldown_until = _cooldown_from_analysis(analysis)
    _persist_answers(session, questions, answers_map, analysis)
    _apply_analysis_to_session(session, analysis, cooldown_until)
    session.submitted_at = timezone.now()
    session.save()

    user.interview_cooldown_until = cooldown_until
    user.save(update_fields=['interview_cooldown_until'])
    return analysis, cooldown_until


def _submit_response_payload(session, analysis, cooldown_until, extra=None):
    payload = {
        'score': session.score or 0,
        'passed': bool(session.passed),
        'technical_score': session.technical_score,
        'personality_score': session.personality_score,
        'attentiveness_score': session.attentiveness_score,
        'eye_contact_score': session.eye_contact_score,
        'communication_score': session.communication_score,
        'confidence_score': session.confidence_score,
        'filler_ratio': session.filler_ratio,
        'cooldown_until': cooldown_until,
        'profile_unlocked': bool(session.passed),
        'hard_fail_triggered': analysis.get('hard_fail_triggered', False),
        'fail_reason': analysis.get('fail_reason'),
        'improvement_plan': session.improvement_plan,
        'progress_report': session.progress_report,
    }
    if extra:
        payload.update(extra)
    return payload


def _previously_used_question_texts(user, job_role=None, experience_band=None):
    """Question prompts from completed attempts for the same role/band."""
    qs = InterviewQuestion.objects.filter(
        session__user=user,
        session__submitted_at__isnull=False,
    )
    if job_role:
        role = normalize_role(job_role)
        qs = qs.filter(session__job_role=role)
    if experience_band:
        qs = qs.filter(session__experience_band=experience_band)

    blocked: set[str] = set()
    for text in qs.values_list('question_text', flat=True):
        cleaned = normalize_question_text(text)
        if not cleaned:
            continue
        blocked.add(cleaned)
        blocked.add(normalize_for_dedupe(cleaned))
    return blocked


def _create_session_from_start_payload(user, start_payload, attempt_number):
    job_role = start_payload['job_role']
    years_experience = float(start_payload['experience_years'])
    experience_band = start_payload.get('experience_band') or experience_band_from_years(years_experience)

    session = InterviewSession.objects.create(
        user=user,
        job_role=job_role,
        years_experience=years_experience,
        experience_band=experience_band,
        attempt_number=attempt_number,
        monitoring_data={},
        answer_timings={},
    )

    for i, q in enumerate(start_payload['questions']):
        InterviewQuestion.objects.create(
            session=session,
            question_text=q['question_text'],
            question_type=q['question_type'],
            category=q.get('category', ''),
            generation_source=q.get('generation_source', 'csv'),
            reference_keywords=q.get('reference_keywords', ''),
            reference_points=q.get('reference_points', ''),
            order=i,
        )
    return session


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_interview(request):
    serializer = StartInterviewSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    if not _user_passed_quiz(user):
        return Response(
            {'error': 'Interview is locked. You must pass the quiz first.', 'quiz_required': True},
            status=status.HTTP_403_FORBIDDEN,
        )

    latest_submitted = _latest_submitted_session(user)
    if latest_submitted and latest_submitted.passed:
        return Response(
            {
                'error': 'You have already passed the interview.',
                'already_passed': True,
                'session_id': latest_submitted.id,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    in_flight = _in_flight_session(user)
    if in_flight:
        questions, time_left = _resume_context(in_flight)
        if time_left > 0:
            return Response(
                {
                    'session_id': in_flight.id,
                    'job_role': in_flight.job_role,
                    'years_experience': in_flight.years_experience,
                    'experience_band': in_flight.experience_band,
                    'questions': InterviewQuestionSerializer(questions, many=True).data,
                    'time_limit_seconds': time_left,
                    'resumed': True,
                },
                status=status.HTTP_200_OK,
            )

        # Expired in-flight session — evaluate with whatever data exists.
        answers_map = {
            str(a.question_id): a.transcript
            for a in InterviewAnswer.objects.filter(session=in_flight).select_related('question')
        }
        if not answers_map:
            answers_map = {str(q.id): '' for q in questions}
        try:
            analysis, cooldown_until = _finalize_session(
                user, in_flight, list(questions), answers_map, interview_expired=True,
            )
        except Exception as exc:
            return Response(
                {'error': 'Interview analysis failed.', 'details': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        latest_submitted = in_flight
        return Response(
            _submit_response_payload(
                in_flight,
                analysis,
                cooldown_until,
                extra={'error': 'Interview time expired.', 'passed': False},
            ),
            status=status.HTTP_200_OK,
        )

    if user.interview_cooldown_until and timezone.now() < user.interview_cooldown_until:
        return Response(
            {
                'error': 'Interview is on cooldown.',
                'cooldown_until': user.interview_cooldown_until,
                'previous_score': latest_submitted.score if latest_submitted else None,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    latest_resume = user.resumes.first()
    job_role = (latest_resume.job_role if latest_resume and latest_resume.job_role else 'Software Engineer')
    years_experience = float(latest_resume.years_experience) if latest_resume else 0.0
    experience_band = experience_band_from_years(years_experience)

    attempt_number = InterviewSession.objects.filter(user=user, submitted_at__isnull=False).count() + 1
    interview_seed = int(user.id) * 1009 + attempt_number * 5179

    try:
        start_payload = prepare_interview_start(
            quiz_passed=True,
            job_role=job_role,
            years_experience=years_experience,
            num_questions=INTERVIEW_NUM_QUESTIONS,
            seed=interview_seed,
            exclude_questions=_previously_used_question_texts(user, job_role, experience_band),
        )
    except Exception as exc:
        return Response(
            {'error': 'Could not generate interview questions.', 'details': str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not start_payload.get('can_start_interview'):
        return Response(
            {'error': start_payload.get('message', 'Interview cannot start.'), 'quiz_required': True},
            status=status.HTTP_403_FORBIDDEN,
        )

    session = _create_session_from_start_payload(user, start_payload, attempt_number)
    questions = InterviewQuestion.objects.filter(session=session).order_by('order')

    return Response(
        {
            'session_id': session.id,
            'job_role': session.job_role,
            'years_experience': session.years_experience,
            'experience_band': session.experience_band,
            'question_selection_mode': start_payload.get('question_selection_mode', 'offline_hybrid'),
            'questions': InterviewQuestionSerializer(questions, many=True).data,
            'time_limit_seconds': INTERVIEW_TIME_LIMIT_SECONDS,
            'resumed': False,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_monitoring(request):
    serializer = SubmitMonitoringSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    session_id = serializer.validated_data['session_id']
    try:
        session = InterviewSession.objects.get(id=session_id, user=request.user, submitted_at__isnull=True)
    except InterviewSession.DoesNotExist:
        return Response({'error': 'Active session not found.'}, status=status.HTTP_404_NOT_FOUND)

    incoming = {
        'samples': serializer.validated_data.get('samples') or [],
        'events': dict(serializer.validated_data.get('events') or {}),
        'flags': dict(serializer.validated_data.get('flags') or {}),
    }
    session.monitoring_data = merge_monitoring_state(session.monitoring_data, incoming)
    session.save(update_fields=['monitoring_data'])

    scores = build_session_meta_from_monitoring(session.monitoring_data)
    return Response(
        {
            'attentiveness_score': scores['attentiveness_score'],
            'eye_contact_score': scores['eye_contact_score'],
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transcribe_answer(request):
    serializer = TranscribeAnswerSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    session_id = serializer.validated_data['session_id']
    question_id = serializer.validated_data['question_id']
    audio = serializer.validated_data['audio']

    try:
        session = InterviewSession.objects.get(id=session_id, user=request.user, submitted_at__isnull=True)
        question = InterviewQuestion.objects.get(id=question_id, session=session)
    except (InterviewSession.DoesNotExist, InterviewQuestion.DoesNotExist):
        return Response({'error': 'Session or question not found.'}, status=status.HTTP_404_NOT_FOUND)

    transcript = transcribe_audio_file(audio)
    InterviewAnswer.objects.update_or_create(
        session=session,
        question=question,
        defaults={'transcript': transcript},
    )
    return Response({'question_id': question.id, 'transcript': transcript}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_interview(request):
    """Accept multipart submit: audio per question + optional text fallback + timings."""
    session_id = request.data.get('session_id')
    if not session_id:
        return Response({'error': 'session_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = InterviewSession.objects.get(id=int(session_id), user=request.user)
    except (InterviewSession.DoesNotExist, ValueError, TypeError):
        return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    if session.submitted_at:
        return Response({'error': 'This session has already been submitted.'}, status=status.HTTP_400_BAD_REQUEST)

    questions = list(InterviewQuestion.objects.filter(session=session).order_by('order'))

    # Parse optional JSON fields from multipart form.
    text_answers = {}
    answer_timings = {}
    try:
        if request.data.get('answers'):
            text_answers = json.loads(request.data.get('answers'))
    except (json.JSONDecodeError, TypeError):
        text_answers = request.data.get('answers') or {}
    if isinstance(text_answers, str):
        try:
            text_answers = json.loads(text_answers)
        except json.JSONDecodeError:
            text_answers = {}

    try:
        if request.data.get('answer_timings'):
            answer_timings = json.loads(request.data.get('answer_timings'))
    except (json.JSONDecodeError, TypeError):
        answer_timings = request.data.get('answer_timings') or {}
    if isinstance(answer_timings, str):
        try:
            answer_timings = json.loads(answer_timings)
        except json.JSONDecodeError:
            answer_timings = {}

    session.answer_timings = {str(k): float(v) for k, v in (answer_timings or {}).items()}
    session.save(update_fields=['answer_timings'])

    # Merge final monitoring payload if sent on submit.
    monitoring_payload = {}
    if request.data.get('monitoring'):
        try:
            monitoring_payload = json.loads(request.data.get('monitoring'))
        except (json.JSONDecodeError, TypeError):
            monitoring_payload = {}
    if monitoring_payload:
        session.monitoring_data = merge_monitoring_state(session.monitoring_data, monitoring_payload)
        session.save(update_fields=['monitoring_data'])

    # Backend STT from uploaded audio files (`audio_<question_id>`).
    audio_uploads = {}
    for question in questions:
        key = f'audio_{question.id}'
        if key in request.FILES:
            audio_uploads[str(question.id)] = request.FILES[key]

    stt_transcripts = transcribe_uploads(audio_uploads) if audio_uploads else {}

    answers_map = {}
    for question in questions:
        qid = str(question.id)
        transcript = (stt_transcripts.get(qid) or text_answers.get(qid) or '').strip()
        answers_map[qid] = transcript

    elapsed_seconds = int((timezone.now() - session.started_at).total_seconds())
    interview_expired = elapsed_seconds >= INTERVIEW_TIME_LIMIT_SECONDS

    try:
        analysis, cooldown_until = _finalize_session(
            request.user,
            session,
            questions,
            answers_map,
            interview_expired=interview_expired,
        )
    except Exception as exc:
        return Response(
            {'error': 'Interview analysis failed.', 'details': str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    extra = {}
    if interview_expired and not session.passed:
        extra['error'] = 'Interview time expired.'

    return Response(
        _submit_response_payload(session, analysis, cooldown_until, extra=extra or None),
        status=status.HTTP_200_OK,
    )


def _feedback_from_session(session):
    """Rebuild candidate-facing feedback using stored scores and session experience."""
    from .services.interview_feedback import generate_improvement_plan, generate_progress_report

    analysis = dict(session.analysis_data or {})
    years = float(session.years_experience or 0)
    band = session.experience_band or experience_band_from_years(years)
    result = {
        **analysis,
        'final_score': session.score,
        'score': session.score,
        'final_decision': 'pass' if session.passed else 'fail',
        'decision': 'pass' if session.passed else 'fail',
        'passed': session.passed,
        'technical_score': session.technical_score,
        'personality_score': session.personality_score,
        'attentiveness_score': session.attentiveness_score,
        'eye_contact_score': session.eye_contact_score,
        'communication_score': session.communication_score,
        'confidence_score': session.confidence_score,
        'filler_ratio': session.filler_ratio,
        'cooldown_days': analysis.get('cooldown_days', 0),
        'job_role': session.job_role,
        'target_role': session.job_role,
        'experience_years': years,
        'years_experience': years,
        'experience_band': band,
        'hard_fail_triggered': analysis.get('hard_fail_triggered', False),
        'fail_reason': analysis.get('fail_reason'),
        'personality_trait': analysis.get('personality_trait', 'Communication'),
    }
    progress_report = generate_progress_report(result)
    improvement_plan = generate_improvement_plan(result, progress_report)
    return progress_report, improvement_plan


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def latest_interview(request):
    latest = _latest_submitted_session(request.user)
    if not latest:
        return Response({'error': 'No completed interview found.'}, status=status.HTTP_404_NOT_FOUND)

    answers = (
        InterviewAnswer.objects
        .filter(session=latest)
        .select_related('question')
        .order_by('question__order')
    )

    per_question_meta = {
        item.get('question_text'): item
        for item in (latest.analysis_data or {}).get('per_question_scores', [])
        if item.get('question_text')
    }

    question_reviews = []
    for a in answers:
        meta = per_question_meta.get(a.question.question_text, {})
        question_reviews.append({
            'question_id': a.question.id,
            'question_text': a.question.question_text,
            'question_type': a.question.question_type,
            'category': a.question.category,
            'transcript': a.transcript,
            'score': a.score,
            'reference_points': a.question.reference_points,
            'reference_match_pct': meta.get('reference_match_pct'),
            'reference_keyword_hits': meta.get('reference_keyword_hits'),
            'reference_keyword_total': meta.get('reference_keyword_total'),
            'hit_keywords': meta.get('hit_keywords', []),
            'missed_keywords': meta.get('missed_keywords', []),
            'semantic_score': meta.get('semantic_score'),
            'semantic_similarity': meta.get('semantic_similarity'),
        })

    progress_report, improvement_plan = _feedback_from_session(latest)

    return Response({
        'session_id': latest.id,
        'job_role': latest.job_role,
        'years_experience': latest.years_experience,
        'experience_band': latest.experience_band or experience_band_from_years(latest.years_experience),
        'attempt_number': latest.attempt_number,
        'score': latest.score,
        'passed': latest.passed,
        'technical_score': latest.technical_score,
        'personality_score': latest.personality_score,
        'attentiveness_score': latest.attentiveness_score,
        'eye_contact_score': latest.eye_contact_score,
        'communication_score': latest.communication_score,
        'confidence_score': latest.confidence_score,
        'filler_ratio': latest.filler_ratio,
        'cooldown_until': latest.cooldown_until,
        'submitted_at': latest.submitted_at,
        'improvement_plan': improvement_plan,
        'progress_report': progress_report,
        'analysis_data': latest.analysis_data,
        'questions': question_reviews,
    })
