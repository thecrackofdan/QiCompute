from __future__ import annotations

from typing import Any


CUSTOMER_CATEGORIES = (
    "privacy_conscious_individuals",
    "local_businesses",
    "ai_developers",
    "researchers",
    "self_hosters",
    "agent_operators",
)


def interview_templates() -> dict[str, list[str]]:
    shared = [
        "What compute tasks do you run today?",
        "What provider or local setup do you use now?",
        "What would make you switch providers?",
        "How sensitive are your prompts, inputs, or outputs?",
        "Would you pay more for local execution or stronger privacy controls?",
        "Would verifiable receipts change your trust in a compute provider?",
        "What latency, reliability, and support requirements would block adoption?",
    ]
    return {
        "privacy_conscious_individuals": shared + [
            "What data would you refuse to send to a centralized AI API?",
            "Do hashes and no raw-output retention address your concern, or do you need stronger guarantees?",
        ],
        "local_businesses": shared + [
            "Which local workflows involve customer, employee, or financial data?",
            "Would a trusted local operator be acceptable for these workloads?",
        ],
        "ai_developers": shared + [
            "What API features are non-negotiable for your applications?",
            "Would marketplace pricing uncertainty prevent integration?",
        ],
        "researchers": shared + [
            "Are your workloads latency-sensitive or batch-oriented?",
            "How do you compare reproducibility, cost, and privacy?",
        ],
        "self_hosters": shared + [
            "How much idle GPU capacity do you have?",
            "What earnings level would justify running a worker?",
        ],
        "agent_operators": shared + [
            "Would your agents buy inference from other agents or operators?",
            "What spending limits and audit controls would you need?",
        ],
    }


def questions_only() -> list[str]:
    questions: list[str] = []
    for category, category_questions in interview_templates().items():
        questions.append(f"[{category}]")
        questions.extend(category_questions)
    return questions


def main() -> None:
    for line in questions_only():
        print(line)


if __name__ == "__main__":
    main()
