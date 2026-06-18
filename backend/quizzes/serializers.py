from rest_framework import serializers
from .models import QuizSession, QuizQuestion

class QuizQuestionSerializer(serializers.ModelSerializer):
    """
    Safe public serializer — correct_answer is deliberately excluded.
    The frontend ONLY receives: id, question_text, question_type, options, difficulty, order.
    """

    class Meta:
        model  = QuizQuestion
        fields = ['id', 'question_text', 'question_type', 'options', 'difficulty', 'order']
        # ↑ correct_answer intentionally absent

class StartQuizSerializer(serializers.Serializer):
    job_role = serializers.CharField(max_length=100, required=False, allow_blank=True)

class SubmitQuizSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    # Keys are question IDs (as strings, per JSON spec); values are chosen option indices
    answers = serializers.DictField(child=serializers.IntegerField(allow_null=True))