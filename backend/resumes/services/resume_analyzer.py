from resumes.services.resume_ai.pipeline import run_pipeline


def analyze_resume_file(file_path, target_role=None, years_of_experience=None):
    result = run_pipeline(
        file_path,
        target_role=target_role,
        years_of_experience=years_of_experience
    )

    if result.get("status") == "error":
        raise ValueError(result.get("message", "Resume analysis failed."))

    if result.get("status") == "rejected":
        raise ValueError(result.get("reason", "Resume rejected."))

    return {
        "score": result.get("resume_score", 0),
        "base_score": result.get("base_score", 0),
        "analysis_log": result.get("analysis_log", []),
        "grade": result.get("grade"),
        "detected_role": result.get("detected_role"),
        "target_role": result.get("target_role"),
        "selected_role": result.get("selected_role"),
        "selected_role_raw": result.get("selected_role_raw"),
        "role_alignment": result.get("role_alignment"),
        "role_penalty": result.get("role_penalty", 0),
        "role_mismatch_block": result.get("role_mismatch_block", False),
        "role_match_message": result.get("role_match_message"),
        "quiz_eligible": result.get("quiz_eligible", False),
        "grammar_count": result.get("grammar_count", 0),
        "grammar_issues": result.get("grammar_issues", []),
        "missing_sections": result.get("missing_sections", []),
        "quality_analysis": result.get("quality_analysis", {}),
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "improvement_plan": result.get("improvement_plan", {}),
        "technical_skills_list": result.get("technical_skills_list", []),
        "social_links": result.get("social_links"),
        "message": result.get("message", ""),
    }