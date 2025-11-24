from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, MutableMapping, Optional

from openai import OpenAI, OpenAIError

import schemas


class SpecialistAgentError(Exception):
    """Base error for specialist agent operations."""


class SpecialistModelError(SpecialistAgentError):
    """Raised when the underlying LLM call fails."""


def _parse_ai_response(raw_text: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"diagnosis": raw_text.strip(), "suggestive_plan": []}


def _normalize_plan(plan_data: Any) -> List[str]:
    if isinstance(plan_data, list):
        return [str(item).strip() for item in plan_data if str(item).strip()]
    if isinstance(plan_data, str) and plan_data.strip():
        return [plan_data.strip()]
    return []


@dataclass
class SpecialistAgent:
    specialist: schemas.SpecialistType
    voice: str
    focus: List[str] = field(default_factory=list)

    def build_system_prompt(self) -> str:
        focus_text = (
            " ".join(self.focus).strip() if any(self.focus) else ""
        )
        return (
            f"You are a board-certified {self.specialist.value} contributing to a liver tumor board. "
            f"{self.voice} {focus_text}".strip()
        )

    def build_user_prompt(self, patient_context: MutableMapping[str, Any]) -> str:
        directive = (
            "You are reviewing the following patient data. "
            "Produce JSON with keys: diagnosis (string), suggestive_plan (array of strings), "
            "confidence (string, optional), caveats (string, optional). "
            "Keep recommendations actionable but concise."
        )
        return f"{directive}\n\nPatient data:\n{json.dumps(patient_context, indent=2)}"

    def generate_summary(
        self,
        patient_context: MutableMapping[str, Any],
        client: OpenAI,
        model_name: str,
    ) -> schemas.SpecialistSummaryResponse:
        try:
            response = client.chat.completions.create(
                model=model_name,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": self.build_system_prompt()},
                    {"role": "user", "content": self.build_user_prompt(patient_context)},
                ],
            )
        except OpenAIError as exc:
            raise SpecialistModelError(f"OpenAI API error: {exc}") from exc

        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""

        parsed = _parse_ai_response(content)
        plan_data = (
            parsed.get("suggestive_plan")
            or parsed.get("plan_of_action")
            or parsed.get("plan")
            or parsed.get("recommendations")
        )
        plan = _normalize_plan(plan_data)
        if not plan:
            plan = [
                "Review with multidisciplinary tumor board for individualized planning."
            ]

        diagnosis = parsed.get("diagnosis") or parsed.get("assessment") or "No diagnosis generated."
        confidence = parsed.get("confidence") or parsed.get("confidence_level")
        caveats = parsed.get("caveats") or parsed.get("risks") or parsed.get("considerations")

        return schemas.SpecialistSummaryResponse(
            specialist=self.specialist,
            diagnosis=diagnosis.strip(),
            suggestive_plan=plan,
            confidence=confidence.strip() if isinstance(confidence, str) else confidence,
            caveats=caveats.strip() if isinstance(caveats, str) else caveats,
            source_model=model_name,
            generated_at=datetime.utcnow(),
        )


SPECIALIST_REGISTRY: Dict[schemas.SpecialistType, SpecialistAgent] = {
    schemas.SpecialistType.oncologist: SpecialistAgent(
        specialist=schemas.SpecialistType.oncologist,
        voice="Offer a cautious, evidence-based assessment grounded in current oncology guidelines.",
        focus=[
            "Highlight staging, systemic therapy options, and trial eligibility where relevant.",
        ],
    ),
    schemas.SpecialistType.hepatologist: SpecialistAgent(
        specialist=schemas.SpecialistType.hepatologist,
        voice="Focus on hepatic reserve, portal hypertension, and transplant candidacy considerations.",
        focus=[
            "Ensure safety considerations for liver-directed therapies are clearly stated.",
        ],
    ),
}


def get_specialist_agent(specialist: schemas.SpecialistType) -> SpecialistAgent:
    try:
        return SPECIALIST_REGISTRY[specialist]
    except KeyError as exc:
        raise SpecialistAgentError(f"No agent registered for specialist '{specialist}'.") from exc


def generate_specialist_summary(
    *,
    specialist: schemas.SpecialistType,
    patient_context: MutableMapping[str, Any],
    client: OpenAI,
    model_name: str,
) -> schemas.SpecialistSummaryResponse:
    agent = get_specialist_agent(specialist)
    return agent.generate_summary(patient_context=patient_context, client=client, model_name=model_name)


