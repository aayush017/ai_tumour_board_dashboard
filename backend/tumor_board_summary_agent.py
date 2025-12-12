import json
from typing import Dict, Any, Optional
from openai import OpenAI

class TumorBoardNotesAgent:

    SYSTEM_PROMPT = """
    You are a Tumor Board Notes Extraction Agent for hepatocellular carcinoma (HCC).

    INPUT:
    - tumor board notes (free text)
    - board member list
    - treatment history

    TASK:
    Summarize the tumor board notes into a structured Schema 1 output.

    RULES:
    - Summary: 4-5 sentences, clinical tone.
    - Include key decisions + rationale + follow-up.
    - Do NOT add data not explicitly stated.
    - Retain board members exactly.
    - Retain treatment history fields, but express response concisely.
    - Output must be valid JSON only.

    STRICT OUTPUT FORMAT:
    {
      "notes_summary": {
        "tumor_board_text": "",
        "treatment_history": {
          "previous": [],
          "current": "",
          "response": ""
        },
        "board_members": []
      }
    }
    """

    def __init__(self, client: OpenAI, model="gpt-4o", temperature=0):
        self.client = client
        self.model = model
        self.temperature = temperature

    def run(self, tumor_board: Dict[str, Any], treatment_history: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "tb_notes_text": tumor_board.get("tb_notes_text", ""),
            "members_present": tumor_board.get("members_present", []),
            "previous_treatments": treatment_history.get("previous_treatments", []),
            "current_treatment": treatment_history.get("current_treatment", ""),
            "treatment_response_notes": treatment_history.get("treatment_response_notes", "")
        }

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)}
            ]
        )

        return json.loads(response.choices[0].message.content)


# Sample usage when run directly (avoids side effects on import)
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    agent = TumorBoardNotesAgent(client=client)

    tumor_board_data = {
        "tb_notes_text": "Patient discussed in TB. Partial response after TACE. Plan to continue immunotherapy and reassess with MRI in 3 months.",
        "members_present": ["Hepatologist", "Radiologist", "Oncologist"]
    }

    treatment_history_data = {
        "previous_treatments": ["TACE"],
        "current_treatment": "Atezolizumab + Bevacizumab",
        "treatment_response_notes": "Partial response after TACE."
    }

    output = agent.run(tumor_board_data, treatment_history_data)
    print(json.dumps(output, indent=2))
