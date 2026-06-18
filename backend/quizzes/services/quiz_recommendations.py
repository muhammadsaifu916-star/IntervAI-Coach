"""
Quiz improvement-plan service.

This converts the original notebook/terminal recommendation idea into structured
JSON that Django can return to the frontend.
"""

from collections import defaultdict
from typing import Any

WEAK_THRESHOLD = 50
STRONG_THRESHOLD = 80
MAX_WEAK_TOPICS = 5
MAX_MISTAKES_PER_TOPIC = 3

TOPIC_STUDY_GUIDE: dict[str, dict[str, list[str]]] = {
    "OOP": {
        "key_concepts": ["Classes & objects", "Inheritance", "Polymorphism", "Encapsulation", "Abstraction", "SOLID principles"],
        "practice_focus": ["Build a small class hierarchy", "Practice overriding and interfaces", "Review design-pattern examples"],
        "resources": ["Refactoring Guru", "Head First Design Patterns", "Clean Code"],
    },
    "DSA": {
        "key_concepts": ["Arrays and linked lists", "Stacks and queues", "Trees and graphs", "Sorting", "Binary search", "Hash tables", "Big-O"],
        "practice_focus": ["Solve 10 LeetCode Easy/Medium problems", "Implement sorting algorithms", "Practice BFS/DFS and recursion"],
        "resources": ["LeetCode", "GeeksForGeeks", "Cracking the Coding Interview"],
    },
    "DBMS": {
        "key_concepts": ["SQL joins", "Normalization", "Keys", "Indexes", "Transactions", "ACID properties"],
        "practice_focus": ["Write JOIN queries", "Design normalized schemas", "Practice transaction/isolation scenarios"],
        "resources": ["SQLZoo", "W3Schools SQL", "Database System Concepts"],
    },
    "Programming Fundamentals": {
        "key_concepts": ["Variables and data types", "Control flow", "Functions", "Recursion", "Error handling", "Time complexity"],
        "practice_focus": ["Solve basic coding problems", "Build small CLI programs", "Trace code by hand"],
        "resources": ["CS50", "Python Docs", "GeeksForGeeks basics"],
    },
    "Python": {
        "key_concepts": ["Data structures", "Functions", "OOP in Python", "Decorators", "Generators", "Virtual environments"],
        "practice_focus": ["Build scripts", "Practice list/dict comprehensions", "Create a simple API or automation task"],
        "resources": ["Real Python", "Python Docs", "Fluent Python"],
    },
    "JavaScript": {
        "key_concepts": ["Closures", "Event loop", "Promises", "Async/await", "DOM", "ES6+ syntax"],
        "practice_focus": ["Build async examples", "Practice DOM events", "Explain the event loop with examples"],
        "resources": ["MDN Web Docs", "javascript.info", "You Don't Know JS"],
    },
    "React": {
        "key_concepts": ["Components", "Props and state", "Hooks", "useEffect", "Rendering", "Performance basics"],
        "practice_focus": ["Build reusable components", "Practice hooks", "Debug rerender issues"],
        "resources": ["React Docs", "Epic React", "MDN Web Docs"],
    },
    "HTML/CSS": {
        "key_concepts": ["Semantic HTML", "Flexbox", "Grid", "Responsive design", "Specificity", "Accessibility"],
        "practice_focus": ["Recreate layouts", "Practice responsive pages", "Improve accessibility labels"],
        "resources": ["MDN Web Docs", "CSS-Tricks", "web.dev"],
    },
    "APIs": {
        "key_concepts": ["REST", "HTTP methods", "Status codes", "Serialization", "Pagination", "Validation"],
        "practice_focus": ["Build CRUD endpoints", "Test APIs with Postman", "Handle errors cleanly"],
        "resources": ["Django REST Framework Docs", "REST API Tutorial", "Postman Learning Center"],
    },
    "Django_Flask": {
        "key_concepts": ["Routing", "Views", "Models", "Serializers/forms", "Authentication", "Middleware"],
        "practice_focus": ["Build CRUD APIs", "Use migrations", "Add authentication and permissions"],
        "resources": ["Django Docs", "DRF Docs", "Flask Docs"],
    },
    "Authentication": {
        "key_concepts": ["JWT", "Sessions", "Password hashing", "Permissions", "Refresh tokens", "CSRF"],
        "practice_focus": ["Implement login/logout", "Protect routes", "Test invalid/expired tokens"],
        "resources": ["OWASP Authentication Cheat Sheet", "SimpleJWT Docs", "Django Auth Docs"],
    },
    "Database": {
        "key_concepts": ["Schema design", "Relationships", "Indexes", "Transactions", "Query optimization"],
        "practice_focus": ["Design relational tables", "Analyze slow queries", "Use migrations carefully"],
        "resources": ["PostgreSQL Docs", "Django ORM Docs", "Use The Index, Luke"],
    },
    "Databases": {
        "key_concepts": ["Relational vs NoSQL", "Schema design", "Indexes", "Transactions", "Backups"],
        "practice_focus": ["Compare SQL/NoSQL use cases", "Design schemas", "Practice indexing examples"],
        "resources": ["PostgreSQL Docs", "MongoDB University", "Database System Concepts"],
    },
    "SQL": {
        "key_concepts": ["SELECT", "JOIN", "GROUP BY", "Subqueries", "Indexes", "Views"],
        "practice_focus": ["Write reporting queries", "Practice joins", "Solve SQL interview questions"],
        "resources": ["SQLZoo", "Mode SQL Tutorial", "LeetCode Database"],
    },
    "Machine Learning basics": {
        "key_concepts": ["Supervised vs unsupervised learning", "Train/test split", "Overfitting", "Metrics", "Feature engineering"],
        "practice_focus": ["Train simple classifiers", "Compare metrics", "Practice preprocessing"],
        "resources": ["scikit-learn Docs", "Kaggle Learn", "Hands-On Machine Learning"],
    },
    "Statistics": {
        "key_concepts": ["Mean/median/mode", "Variance", "Probability", "Distributions", "Hypothesis testing"],
        "practice_focus": ["Solve probability problems", "Interpret charts", "Practice confidence intervals"],
        "resources": ["Khan Academy Statistics", "StatQuest", "OpenIntro Statistics"],
    },
    "Pandas_NumPy": {
        "key_concepts": ["DataFrames", "Filtering", "GroupBy", "Merging", "Vectorization", "Missing values"],
        "practice_focus": ["Clean a CSV dataset", "Perform groupby analysis", "Use vectorized operations"],
        "resources": ["Pandas Docs", "NumPy Docs", "Kaggle Learn Pandas"],
    },
    "Data Visualization": {
        "key_concepts": ["Chart selection", "Axes", "Outliers", "Dashboards", "Storytelling"],
        "practice_focus": ["Create charts from datasets", "Explain insights", "Avoid misleading visuals"],
        "resources": ["Matplotlib Docs", "Tableau Public", "Storytelling with Data"],
    },
    "Excel": {
        "key_concepts": ["Formulas", "Pivot tables", "Lookups", "Charts", "Cleaning data"],
        "practice_focus": ["Build dashboards", "Practice pivot tables", "Use lookup formulas"],
        "resources": ["Microsoft Excel Help", "ExcelJet", "Chandoo"],
    },
    "Docker": {
        "key_concepts": ["Images", "Containers", "Dockerfile", "Volumes", "Networks", "Compose"],
        "practice_focus": ["Dockerize a web app", "Use docker-compose", "Debug container logs"],
        "resources": ["Docker Docs", "Play with Docker", "Docker Curriculum"],
    },
    "CI_CD": {
        "key_concepts": ["Pipelines", "Build stages", "Testing", "Deployment", "Rollback", "Secrets"],
        "practice_focus": ["Create a GitHub Actions workflow", "Automate tests", "Deploy a small app"],
        "resources": ["GitHub Actions Docs", "GitLab CI Docs", "Atlassian CI/CD Guide"],
    },
    "Cloud basics": {
        "key_concepts": ["IaaS/PaaS/SaaS", "Compute", "Storage", "Networking", "Scaling", "Monitoring"],
        "practice_focus": ["Deploy a small service", "Understand pricing basics", "Practice cloud architecture diagrams"],
        "resources": ["AWS Skill Builder", "Microsoft Learn", "Google Cloud Skills Boost"],
    },
    "Linux": {
        "key_concepts": ["Shell commands", "Permissions", "Processes", "Services", "Logs", "Networking"],
        "practice_focus": ["Use common commands", "Manage permissions", "Read logs and troubleshoot services"],
        "resources": ["Linux Journey", "The Linux Command Line", "Ubuntu Docs"],
    },
    "Network Security": {
        "key_concepts": ["Firewalls", "Ports", "TLS", "VPNs", "IDS/IPS", "Threats"],
        "practice_focus": ["Analyze network scenarios", "Review common attacks", "Practice secure configuration"],
        "resources": ["OWASP", "Cisco Networking Basics", "PortSwigger Web Security Academy"],
    },
    "OWASP": {
        "key_concepts": ["Injection", "Broken access control", "XSS", "CSRF", "Security misconfiguration"],
        "practice_focus": ["Study OWASP Top 10", "Practice secure validation", "Test vulnerable apps safely"],
        "resources": ["OWASP Top 10", "PortSwigger Academy", "Web Security Testing Guide"],
    },
    "Cryptography basics": {
        "key_concepts": ["Hashing", "Encryption", "Symmetric/asymmetric keys", "Digital signatures", "TLS"],
        "practice_focus": ["Compare hashing vs encryption", "Review key exchange", "Practice security MCQs"],
        "resources": ["Crypto 101", "OWASP Cryptographic Storage", "Khan Academy Cryptography"],
    },
    "Blockchain": {
        "key_concepts": ["Blocks", "Hashing", "Consensus", "Wallets", "Smart contracts", "Gas"],
        "practice_focus": ["Explain blockchain flow", "Review consensus algorithms", "Analyze smart contract use cases"],
        "resources": ["Ethereum Docs", "Solidity Docs", "Mastering Bitcoin"],
    },
    "Solidity": {
        "key_concepts": ["Contracts", "State variables", "Functions", "Modifiers", "Events", "Security risks"],
        "practice_focus": ["Write simple contracts", "Practice modifiers/events", "Review reentrancy examples"],
        "resources": ["Solidity Docs", "CryptoZombies", "OpenZeppelin Docs"],
    },
    "Testing": {
        "key_concepts": ["Unit testing", "Integration testing", "Test cases", "Automation", "Regression", "Bug reports"],
        "practice_focus": ["Write test cases", "Automate simple tests", "Practice bug reporting"],
        "resources": ["ISTQB Foundation", "Selenium Docs", "pytest Docs"],
    },
    "UI_UX_Basics": {
        "key_concepts": ["User flows", "Wireframes", "Usability", "Accessibility", "Visual hierarchy", "Design systems"],
        "practice_focus": ["Create wireframes", "Review app usability", "Improve accessibility and consistency"],
        "resources": ["Nielsen Norman Group", "Material Design", "Figma Learn"],
    },
    "Java": {
        "key_concepts": ["OOP", "Collections", "Exceptions", "Streams", "JVM", "Multithreading"],
        "practice_focus": ["Build Java classes", "Practice collections", "Solve stream/lambda problems"],
        "resources": ["Java Docs", "Effective Java", "Baeldung"],
    },
    "Spring Boot": {
        "key_concepts": ["Controllers", "Services", "Repositories", "Dependency injection", "REST APIs", "Configuration"],
        "practice_focus": ["Build REST endpoints", "Connect a database", "Write service-layer tests"],
        "resources": ["Spring Guides", "Baeldung Spring", "Spring Boot Docs"],
    },
    "Mobile Development": {
        "key_concepts": ["Activity/lifecycle basics", "Navigation", "State", "API calls", "Local storage", "Responsive UI"],
        "practice_focus": ["Build a simple mobile screen", "Call an API", "Handle navigation/state"],
        "resources": ["Android Developers", "React Native Docs", "Flutter Docs"],
    },
    "Git_GitHub": {
        "key_concepts": ["Commits", "Branches", "Merging", "Pull requests", "Conflicts", "GitHub workflow"],
        "practice_focus": ["Practice branching", "Resolve merge conflicts", "Create pull requests"],
        "resources": ["Pro Git Book", "GitHub Docs", "Atlassian Git Tutorials"],
    },
    "Database Optimization": {
        "key_concepts": ["Indexes", "Query plans", "Caching", "Normalization tradeoffs", "Slow-query analysis"],
        "practice_focus": ["Use EXPLAIN", "Add indexes", "Compare query performance"],
        "resources": ["Use The Index, Luke", "PostgreSQL EXPLAIN Docs", "Django ORM optimization docs"],
    },
    "DBM": {
        "key_concepts": ["SQL", "Schema design", "Indexes", "Constraints", "Transactions"],
        "practice_focus": ["Practice database design", "Write SQL queries", "Review constraints and indexes"],
        "resources": ["SQLZoo", "PostgreSQL Docs", "Database System Concepts"],
    },
}

DEFAULT_STUDY_GUIDE = {
    "key_concepts": ["Review the core concepts", "Study the related subtopics", "Practice common interview questions"],
    "practice_focus": ["Revise notes", "Practice MCQs", "Build a small example project"],
    "resources": ["Official documentation", "GeeksForGeeks", "YouTube tutorials"],
}


def _answer_text(question: Any, answer_index: int | None) -> str | None:
    options = question.options or []
    if answer_index is None:
        return None
    if 0 <= answer_index < len(options):
        return options[answer_index]
    return None


def build_quiz_improvement_plan(answer_records, weak_threshold: int = WEAK_THRESHOLD) -> dict[str, Any]:
    """Build topic performance + personalized study plan from QuizAnswer records."""
    topic_scores: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "wrong": 0})
    wrong_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for answer in answer_records:
        question = answer.question
        topic = (question.topic or "General").strip() or "General"

        if answer.is_correct:
            topic_scores[topic]["correct"] += 1
        else:
            topic_scores[topic]["wrong"] += 1
            if len(wrong_by_topic[topic]) < MAX_MISTAKES_PER_TOPIC:
                wrong_by_topic[topic].append({
                    "question_text": question.question_text,
                    "selected_answer_text": _answer_text(question, answer.selected_answer) or "Not answered",
                    "correct_answer_text": _answer_text(question, question.correct_answer) or "N/A",
                    "explanation": question.explanation or "Review this concept and compare your answer with the correct option.",
                })

    topic_performance: list[dict[str, Any]] = []
    for topic, counts in topic_scores.items():
        correct = counts["correct"]
        wrong = counts["wrong"]
        total = correct + wrong
        accuracy = round((correct / total) * 100, 1) if total else 0.0

        if accuracy >= STRONG_THRESHOLD:
            strength = "Strong"
        elif accuracy >= weak_threshold:
            strength = "Average"
        else:
            strength = "Weak"

        topic_performance.append({
            "topic": topic,
            "correct": correct,
            "wrong": wrong,
            "total": total,
            "accuracy": accuracy,
            "strength": strength,
            "is_weak": accuracy < weak_threshold,
        })

    topic_performance.sort(key=lambda item: (item["is_weak"], item["wrong"], -item["accuracy"]), reverse=True)

    weak_topics = [item["topic"] for item in topic_performance if item["is_weak"]]

    # If there are no <50% topics but the user failed overall, still recommend the weakest topics.
    if not weak_topics and topic_performance:
        weak_topics = [item["topic"] for item in sorted(topic_performance, key=lambda item: (item["accuracy"], -item["wrong"]))[:2]]

    weak_topics = weak_topics[:MAX_WEAK_TOPICS]

    study_plan = []
    for index, topic in enumerate(weak_topics, start=1):
        guide = TOPIC_STUDY_GUIDE.get(topic, DEFAULT_STUDY_GUIDE)
        study_plan.append({
            "priority": index,
            "topic": topic,
            "key_concepts": guide["key_concepts"],
            "practice_focus": guide["practice_focus"],
            "resources": guide["resources"],
            "mistakes_to_review": wrong_by_topic.get(topic, []),
            "suggested_day": f"Day {index}",
            "suggested_time": "2 hours",
        })

    if study_plan:
        summary = "Focus first on the topics where your accuracy was below 50%, then retake the quiz after revision."
    else:
        summary = "Great performance. No major weak area was detected, so keep practicing mixed questions to maintain consistency."

    return {
        "topic_performance": topic_performance,
        "weak_topics": weak_topics,
        "study_plan": study_plan,
        "summary": summary,
    }
