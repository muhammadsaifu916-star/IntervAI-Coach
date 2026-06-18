from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from .models import QuizSession, QuizQuestion, QuizAnswer
from .serializers import QuizQuestionSerializer, StartQuizSerializer, SubmitQuizSerializer
from .services.quiz_generator import generate_quiz_questions
from .services.quiz_recommendations import build_quiz_improvement_plan

QUIZ_NUM_QUESTIONS = 15
QUIZ_TIME_LIMIT_SECONDS = 1200
RESUME_SCORE_REQUIRED = 70
QUIZ_PASS_THRESHOLD = 70
QUIZ_LOW_SCORE_THRESHOLD = 50
COOLDOWN_DAYS_LOW_SCORE = 3   # score < 50
COOLDOWN_DAYS_MID_SCORE = 1   # 50 ≤ score < 70
COOLDOWN_DAYS_EXPIRED = 3


def _cooldown_for_score(score):
    """Return the cooldown timedelta for a failing score, or None if passed."""
    if score >= QUIZ_PASS_THRESHOLD:
        return None
    days = COOLDOWN_DAYS_LOW_SCORE if score < QUIZ_LOW_SCORE_THRESHOLD else COOLDOWN_DAYS_MID_SCORE
    return timedelta(days=days)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_quiz(request):
    """
    Gate: resume_score >= RESUME_SCORE_REQUIRED, no active cooldown, and no already-passed quiz.
    If an unfinished quiz session exists, resume it instead of creating a new one.
    """
    serializer = StartQuizSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Gate 1: resume score ──
    latest_resume = request.user.resumes.first()

    if not latest_resume or (latest_resume.score or 0) < RESUME_SCORE_REQUIRED:
        return Response(
            {'error': f'Quiz is locked. Your resume score must be {RESUME_SCORE_REQUIRED} or above.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Check latest submitted quiz ──
    latest_submitted_session = (
        QuizSession.objects
        .filter(user=request.user, submitted_at__isnull=False)
        .order_by('-submitted_at')
        .first()
    )

    # ── Gate 2: user already passed quiz ──
    if latest_submitted_session and latest_submitted_session.passed:
        return Response(
            {
                'error': 'You have already passed the quiz.',
                'already_passed': True,
                'session_id': latest_submitted_session.id,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Resume unfinished quiz instead of creating a new one ──
    in_flight_session = (
        QuizSession.objects
        .filter(user=request.user, submitted_at__isnull=True)
        .order_by('-started_at')
        .first()
    )

    if in_flight_session:
        questions = QuizQuestion.objects.filter(session=in_flight_session).order_by('order')

        elapsed_seconds = int((timezone.now() - in_flight_session.started_at).total_seconds())
        time_left = QUIZ_TIME_LIMIT_SECONDS - elapsed_seconds

        if time_left > 0:
            return Response(
                {
                    'session_id': in_flight_session.id,
                    'questions': QuizQuestionSerializer(questions, many=True).data,
                    'time_limit_seconds': time_left,
                    'resumed': True,
                    'job_role': in_flight_session.job_role,
                    'attempt_number': in_flight_session.attempt_number,
                },
                status=status.HTTP_200_OK,
            )

        # If unfinished quiz expired, auto-submit it as failed
        QuizAnswer.objects.filter(session=in_flight_session).delete()

        for question in questions:
            QuizAnswer.objects.create(
                session=in_flight_session,
                question=question,
                selected_answer=None,
                is_correct=False,
            )

        in_flight_session.score = 0
        in_flight_session.passed = False
        in_flight_session.cooldown_until = timezone.now() + timedelta(days=COOLDOWN_DAYS_EXPIRED)
        in_flight_session.submitted_at = timezone.now()
        in_flight_session.save(
            update_fields=['score', 'passed', 'cooldown_until', 'submitted_at']
        )

        request.user.quiz_cooldown_until = in_flight_session.cooldown_until
        request.user.save(update_fields=['quiz_cooldown_until'])

        latest_submitted_session = in_flight_session

    # ── Gate 3: cooldown (lives on the user, survives resume re-upload) ──
    if request.user.quiz_cooldown_until and timezone.now() < request.user.quiz_cooldown_until:
        return Response(
            {
                'error': 'Quiz is on cooldown.',
                'cooldown_until': request.user.quiz_cooldown_until,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Create new quiz only if allowed ──
    job_role = latest_resume.job_role or 'Software Engineer'

    attempt_number = (
        QuizSession.objects
        .filter(user=request.user, submitted_at__isnull=False)
        .count()
        + 1
    )

    questions_data = generate_quiz_questions(
        job_role=job_role,
        years_experience=latest_resume.years_experience,
        num_questions=QUIZ_NUM_QUESTIONS,
    )

    session = QuizSession.objects.create(
        user=request.user,
        job_role=job_role,
        attempt_number=attempt_number,
    )

    for i, q in enumerate(questions_data):
        QuizQuestion.objects.create(
            session=session,
            question_text=q['text'],
            question_type=q['type'],
            options=q['options'],
            correct_answer=q['correct_answer'],
            difficulty=q['difficulty'],
            topic=q.get('topic', ''),
            subtopic=q.get('subtopic', ''),
            explanation=q.get('explanation', ''),
            order=i,
        )

    questions = QuizQuestion.objects.filter(session=session).order_by('order')

    return Response(
        {
            'session_id': session.id,
            'questions': QuizQuestionSerializer(questions, many=True).data,
            'time_limit_seconds': QUIZ_TIME_LIMIT_SECONDS,
            'resumed': False,
            'job_role': session.job_role,
            'attempt_number': session.attempt_number,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_quiz(request):
    """
    Receives { session_id, answers: { "question_id": chosen_index, ... } }.
    Grades server-side, applies cooldown on failure, returns score.
    """
    serializer = SubmitQuizSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    session_id = serializer.validated_data['session_id']
    answers    = serializer.validated_data['answers']   # { str(q_id): int }

    # ── Validate session ownership ──
    try:
        session = QuizSession.objects.get(id=session_id, user=request.user)
    except QuizSession.DoesNotExist:
        return Response({'error': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

    if session.submitted_at:
        return Response({'error': 'This quiz session has already been submitted.'}, status=status.HTTP_400_BAD_REQUEST)

    questions = QuizQuestion.objects.filter(session=session).order_by('order')

    elapsed_seconds = int((timezone.now() - session.started_at).total_seconds())

    if elapsed_seconds >= QUIZ_TIME_LIMIT_SECONDS:
        QuizAnswer.objects.filter(session=session).delete()

        for question in questions:
            QuizAnswer.objects.create(
                session=session,
                question=question,
                selected_answer=None,
                is_correct=False,
            )

        cooldown_until = timezone.now() + timedelta(days=COOLDOWN_DAYS_EXPIRED)

        session.score = 0
        session.passed = False
        session.cooldown_until = cooldown_until
        session.submitted_at = timezone.now()
        session.save(update_fields=['score', 'passed', 'cooldown_until', 'submitted_at'])

        request.user.quiz_cooldown_until = cooldown_until
        request.user.save(update_fields=['quiz_cooldown_until'])

        expired_answer_records = (
            QuizAnswer.objects
            .filter(session=session)
            .select_related('question')
            .order_by('question__order')
        )

        return Response(
            {
                'session_id': session.id,
                'score': 0,
                'passed': False,
                'correct': 0,
                'total': questions.count(),
                'interview_unlocked': False,
                'cooldown_until': cooldown_until,
                'job_role': session.job_role,
                'attempt_number': session.attempt_number,
                'improvement_plan': build_quiz_improvement_plan(expired_answer_records),
                'error': 'Quiz time expired.',
            },
            status=status.HTTP_200_OK,
        )

    correct_count = 0
    total = questions.count()

    # Safety: remove any old answer records for this session
    QuizAnswer.objects.filter(session=session).delete()

    for question in questions:
        selected_answer = answers.get(str(question.id))

        try:
            selected_answer = int(selected_answer)
        except (TypeError, ValueError):
            selected_answer = None

        is_correct = (
            selected_answer is not None and
            selected_answer == question.correct_answer
        )

        if is_correct:
            correct_count += 1

        QuizAnswer.objects.create(
            session=session,
            question=question,
            selected_answer=selected_answer,
            is_correct=is_correct
        )

    correct = correct_count
    score = round((correct / total) * 100, 1) if total > 0 else 0.0
    passed = score >= QUIZ_PASS_THRESHOLD

    # ── Cooldown based on score tier ──
    cooldown_delta = _cooldown_for_score(score)
    cooldown_until = timezone.now() + cooldown_delta if cooldown_delta else None

    session.score = score
    session.passed = passed
    session.cooldown_until = cooldown_until
    session.submitted_at = timezone.now()
    session.save(update_fields=['score', 'passed', 'cooldown_until', 'submitted_at'])

    # Authoritative cooldown lives on the user so it survives resume re-upload.
    # (On a pass, cooldown_until is None, which harmlessly clears it.)
    request.user.quiz_cooldown_until = cooldown_until
    request.user.save(update_fields=['quiz_cooldown_until'])

    answer_records = (
        QuizAnswer.objects
        .filter(session=session)
        .select_related('question')
        .order_by('question__order')
    )

    return Response(
        {
            'session_id':          session.id,
            'score':               score,
            'passed':              passed,
            'correct':             correct,
            'total':               total,
            'interview_unlocked':  passed,
            'cooldown_until':      cooldown_until,
            'job_role':            session.job_role,
            'attempt_number':      session.attempt_number,
            'improvement_plan':    build_quiz_improvement_plan(answer_records),
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def latest_quiz(request):
    latest_session = (
        QuizSession.objects
        .filter(user=request.user, submitted_at__isnull=False)
        .order_by('-submitted_at')
        .first()
    )

    if not latest_session:
        return Response(
            {'error': 'No completed quiz found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    answer_records = (
        QuizAnswer.objects
        .filter(session=latest_session)
        .select_related('question')
        .order_by('question__order')
    )

    total = QuizQuestion.objects.filter(session=latest_session).count()
    correct = answer_records.filter(is_correct=True).count()

    question_reviews = []

    for answer in answer_records:
        question = answer.question
        options = question.options or []

        selected_answer_text = None
        correct_answer_text = None

        if answer.selected_answer is not None and 0 <= answer.selected_answer < len(options):
            selected_answer_text = options[answer.selected_answer]

        if question.correct_answer is not None and 0 <= question.correct_answer < len(options):
            correct_answer_text = options[question.correct_answer]

        question_reviews.append({
            'question_id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'options': options,
            'selected_answer': answer.selected_answer,
            'selected_answer_text': selected_answer_text,
            'correct_answer': question.correct_answer,
            'correct_answer_text': correct_answer_text,
            'is_correct': answer.is_correct,
            'difficulty': question.difficulty,
            'topic': question.topic,
            'subtopic': question.subtopic,
            'explanation': question.explanation,
        })

    improvement_plan = build_quiz_improvement_plan(answer_records)

    return Response({
        'session_id': latest_session.id,
        'score': latest_session.score,
        'passed': latest_session.passed,
        'correct': correct,
        'total': total,
        'cooldown_until': latest_session.cooldown_until,
        'submitted_at': latest_session.submitted_at,
        'interview_unlocked': latest_session.passed,
        'questions': question_reviews,
        'job_role': latest_session.job_role,
        'attempt_number': latest_session.attempt_number,
        'improvement_plan': improvement_plan,
    })