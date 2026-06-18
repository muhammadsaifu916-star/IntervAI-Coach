from rest_framework import serializers
from .models import InterviewSession, InterviewQuestion, InterviewAnswer


class InterviewQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InterviewQuestion
        fields = ['id', 'question_text', 'question_type', 'category', 'generation_source', 'order']


class StartInterviewSerializer(serializers.Serializer):
    pass  # No input required; job_role is inferred from the user's latest resume


class MonitoringSampleSerializer(serializers.Serializer):
    attentive = serializers.BooleanField()
    eye_contact = serializers.BooleanField()


class MonitoringEventsSerializer(serializers.Serializer):
    tab_switches = serializers.IntegerField(min_value=0, required=False, default=0)
    window_blur_events = serializers.IntegerField(min_value=0, required=False, default=0)
    screenshot_attempted = serializers.IntegerField(min_value=0, required=False, default=0)
    device_detected = serializers.IntegerField(min_value=0, required=False, default=0)
    gaze_off_over_20s = serializers.IntegerField(min_value=0, required=False, default=0)
    english_only_violation = serializers.IntegerField(min_value=0, required=False, default=0)


class MonitoringFlagsSerializer(serializers.Serializer):
    camera_available = serializers.IntegerField(min_value=0, max_value=1, required=False, default=1)
    mic_available = serializers.IntegerField(min_value=0, max_value=1, required=False, default=1)
    terminated_by_violation = serializers.BooleanField(required=False, default=False)


class SubmitMonitoringSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    samples = MonitoringSampleSerializer(many=True, required=False, default=list)
    events = MonitoringEventsSerializer(required=False)
    flags = MonitoringFlagsSerializer(required=False)


class TranscribeAnswerSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    question_id = serializers.IntegerField()
    audio = serializers.FileField()


class SubmitInterviewSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    # Optional text fallback when STT is unavailable; backend STT from audio is preferred.
    answers = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False, default=dict)
    answer_timings = serializers.DictField(child=serializers.FloatField(min_value=0), required=False, default=dict)

    # Legacy direct score fields are ignored — backend computes from monitoring_data.
    attentiveness_score = serializers.FloatField(min_value=0, max_value=100, required=False)
    eye_contact_score = serializers.FloatField(min_value=0, max_value=100, required=False)
    tab_switches = serializers.IntegerField(min_value=0, required=False)
    window_blur_events = serializers.IntegerField(min_value=0, required=False)
    screenshot_attempted = serializers.IntegerField(min_value=0, required=False)
    device_detected = serializers.IntegerField(min_value=0, required=False)
    gaze_off_over_20s = serializers.IntegerField(min_value=0, required=False)
    camera_available = serializers.IntegerField(min_value=0, max_value=1, required=False)
    mic_available = serializers.IntegerField(min_value=0, max_value=1, required=False)
    english_only_violation = serializers.IntegerField(min_value=0, required=False)
    terminated_by_violation = serializers.BooleanField(required=False, default=False)
