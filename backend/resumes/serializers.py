from rest_framework import serializers
from .models import Resume

class ResumeUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = ['job_role', 'years_experience', 'file']

    def validate_file(self, value):
        is_pdf = (
            value.content_type == 'application/pdf'
            and value.name.lower().endswith('.pdf')
        )

        if not is_pdf:
            raise serializers.ValidationError(
                'Only PDF files are allowed.'
            )

        max_size = 10 * 1024 * 1024  # 10 MB
        if value.size > max_size:
            raise serializers.ValidationError(
                'File size must be under 10 MB.'
            )

        return value


class ResumeDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = [
            'id',
            'job_role',
            'years_experience',
            'file',
            'score',
            'feedback',

            # AI resume analysis fields
            'grade',
            'detected_role',
            'strengths',
            'weaknesses',
            'improvement_plan',
            'quality_analysis',
            'grammar_issues',
            'missing_sections',
            'analysis_data',

            'created_at',
        ]
        read_only_fields = [
            'id',
            'score',
            'feedback',
            'grade',
            'detected_role',
            'strengths',
            'weaknesses',
            'improvement_plan',
            'quality_analysis',
            'grammar_issues',
            'missing_sections',
            'analysis_data',
            'created_at',
        ]