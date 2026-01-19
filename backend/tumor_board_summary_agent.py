import json
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # load .env file if present
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

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

    def __init__(self, model="gpt-4o", temperature=0):
        
        self.model = model
        self.temperature = temperature

    def run(self, tumor_board, treatment_history):
        
        payload = {
            "tb_notes_text": tumor_board.get("tb_notes_text", ""),
            "members_present": tumor_board.get("members_present", []),
            "previous_treatments": treatment_history.get("previous_treatments", []),
            "current_treatment": treatment_history.get("current_treatment", ""),
            "treatment_response_notes": treatment_history.get("treatment_response_notes", "")
        }

        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)}
            ]
        )

        return json.loads(response.choices[0].message.content)


agent = TumorBoardNotesAgent()


tumor_board_data = {
    "tb_notes_text": "Case discussed in multidisciplinary tumor board including hepatologists, hepatobiliary surgeons, interventional radiologists, medical oncologists, radiation oncologists, pathologists, and radiologists. Diagnosis: HCV-related cirrhosis with 4.5 cm LI-RADS LR-5 HCC, Child-Pugh class A (score 6). BCLC stage A. Initial therapy: TACE. Post-treatment imaging showed partial response with LR-TR viable residual tumor. Recommendation: repeat locoregional therapy if feasible; systemic immunotherapy if disease progresses. Continue AFP and PIVKA-II monitoring and contrast-enhanced CT/MRI every 2–3 months.",
    "members_present": [
      "Hepatologist",
      "Hepatobiliary Surgeon",
      "Interventional Radiologist",
      "Medical Oncologist",
      "Radiation Oncologist",
      "Pathologist",
      "Radiologist"
    ]
  }

treatment_history_data = {
    "previous_treatments": [
      "TACE"
    ],
    "current_treatment": None,
    "treatment_response_notes": "Post-TACE partial response with residual viable tumor (LI-RADS TR Viable). Overall response described as partial response with viable enhancing component."
  }

output = agent.run(tumor_board_data, treatment_history_data)
print(json.dumps(output, indent=2))
