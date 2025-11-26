import json
import re
from typing import Dict, Any, Optional
from openai import OpenAI
import os


from dotenv import load_dotenv

load_dotenv()  # load .env file if present
api_key = os.getenv("OPENAI_API_KEY")

# =================================================================
#  PATHOLOGY & MOLECULAR EXTRACTION AGENT (GPT-4o-mini + GPT-4o)
# =================================================================

class PathologyMolecularAgent:
    """
    Pathology & Molecular Extraction Agent for HCC Tumor Board Pipeline.
    Converts Schema 2.5 'pathology' block into Schema 1 'pathology_summary'.
    """

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize the agent with OpenAI API.
        Uses GPT-4o-mini for extraction/filling and GPT-4o for interpretation.
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.extract_model = "gpt-4o-mini"   # optimized for deterministic structured JSON extraction
        self.interpret_model = "gpt-4o"      # high-quality summarization

    # -----------------------------------------------------------------
    #  PUBLIC ENTRY POINT
    # -----------------------------------------------------------------
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing pipeline for pathology and molecular extraction.
        input_data: Schema 2.5 input
        Returns Schema 1 pathology_summary JSON.
        """

        pathology_data = input_data.get("pathology", {})
        biopsy_performed = pathology_data.get("biopsy_performed", False)

        # If no biopsy, return empty schema
        if not biopsy_performed:
            return self._create_no_biopsy_output()

        biopsy_markers = pathology_data.get("biopsy_markers", {})
        pathology_text = pathology_data.get("pathology_report_text", "")
        molecular_text = pathology_data.get("molecular_profile_text", "")

        # ----- Initialize object with structured data -----
        pathology_summary = self._initialize_pathology_summary(
            biopsy_markers, pathology_text, molecular_text
        )

        # ----- Apply regex-based extraction before LLM (cheap, fast) -----
        self._regex_extract_histology(pathology_text, pathology_summary["histology"])

        # ----- Run LLM extraction to fill missing fields (using GPT-4o-mini) -----
        llm_extracted = self._llm_extract_all(
            pathology_text=pathology_text,
            molecular_text=molecular_text,
            existing=pathology_summary
        )

        # Merge LLM extraction into summary
        self._merge_llm_extraction(pathology_summary, llm_extracted)

        # ----- Store source texts -----
        pathology_summary["source_text"] = {
            "pathology_report_text": pathology_text,
            "molecular_profile_text": molecular_text
        }

        # ----- Interpretation using GPT-4o -----
        pathology_summary["pathology_interpretation"] = \
            self._generate_interpretation(pathology_summary)

        # ----- Confidence -----
        pathology_summary["agent_metadata"] = {"pathology_agent_confidence":\
            self._calculate_confidence(pathology_summary, biopsy_markers,
                                       pathology_text, molecular_text)}

        return {"pathology_summary": pathology_summary}

    # =================================================================
    #  NO BIOPSY CASE
    # =================================================================
    def _create_no_biopsy_output(self) -> Dict[str, Any]:
        return {
            "pathology_summary": {
                "biopsy_performed": False,
                "histology": {
                    "diagnosis": None,
                    "differentiation": None,
                    "fibrosis_stage": None,
                    "steatosis_percent": None,
                    "steatosis_grade": None,
                    "lobular_inflammation": None,
                    "ballooning": None,
                    "vascular_invasion": None,
                    "comments": "No biopsy performed."
                },
                "molecular_profile": {
                    "TERT_promoter_mutation": "not_reported",
                    "TP53_mutation": "not_reported",
                    "CTNNB1_mutation": "not_reported",
                    "MSI_status": "not_reported",
                    "PDL1_IHC": "not_reported",
                    "TMB": "not_reported"
                },
                "source_text": {
                    "pathology_report_text": "",
                    "molecular_profile_text": ""
                },
                "pathology_interpretation": "No biopsy performed; pathology data unavailable.",
                "agent_metadata": {"pathology_agent_confidence": 1.0}
            }
        }

    # =================================================================
    #  SUMMARY INITIALIZATION
    # =================================================================
    def _initialize_pathology_summary(self, markers, path_text, mol_text):
        diff = self._normalize_differentiation(markers.get("differentiation"))
        fib = self._normalize_fibrosis_stage(markers.get("fibrosis_stage"))
        percent = markers.get("steatosis_percent")
        grade = markers.get("steatosis_grade")
        if percent is not None and grade is None:
            grade = self._calculate_steatosis_grade(percent)

        return {
            "biopsy_performed": True,
            "histology": {
                "diagnosis": None,
                "differentiation": diff,
                "fibrosis_stage": fib,
                "steatosis_percent": percent,
                "steatosis_grade": grade,
                "lobular_inflammation": markers.get("lobular_inflammation"),
                "ballooning": markers.get("ballooning"),
                "vascular_invasion": markers.get("vascular_invasion"),
                "comments": ""
            },
            "molecular_profile": {
                "TERT_promoter_mutation": "not_reported",
                "TP53_mutation": "not_reported",
                "CTNNB1_mutation": "not_reported",
                "MSI_status": "not_reported",
                "PDL1_IHC": "not_reported",
                "TMB": "not_reported"
            },
            "source_text": {},
            "pathology_interpretation": "",
            "agent_metadata": {"pathology_agent_confidence":0.0}
        }

    # =================================================================
    #  NORMALIZATION HELPERS
    # =================================================================
    def _normalize_differentiation(self, diff: Optional[str]):
        if not diff:
            return None
        d = diff.lower()
        if "well" in d:
            return "Well"
        if "mod" in d:
            return "Moderately differentiated"
        if "poor" in d:
            return "Poor"
        if "undiff" in d:
            return "Undifferentiated"
        return None

    def _normalize_fibrosis_stage(self, stage: Optional[str]):
        if not stage:
            return None
        s = stage.upper()
        if s in ["F0", "F1", "F2", "F3", "F4"]:
            return s
        m = re.search(r"[0-4]", s)
        return f"F{m.group()}" if m else None

    def _calculate_steatosis_grade(self, pct: float):
        if pct < 5:
            return 0
        if pct < 33:
            return 1
        if pct < 66:
            return 2
        return 3

    # =================================================================
    #  REGEX PRE-EXTRACTION
    # =================================================================
    def _regex_extract_histology(self, text, hist_out):
        if not text:
            return

        lower = text.lower()

        # Diagnosis
        if "hepatocellular carcinoma" in lower or "hcc" in lower:
            hist_out["diagnosis"] = "Hepatocellular carcinoma"

        # Fibrosis
        if "cirrhosis" in lower or "cirrhotic" in lower:
            hist_out["fibrosis_stage"] = "F4"
        elif "bridging fibrosis" in lower:
            hist_out["fibrosis_stage"] = "F3"

        # Vascular invasion
        if "no vascular invasion" in lower:
            hist_out["vascular_invasion"] = False
        elif "microvascular invasion" in lower or "mvi" in lower:
            hist_out["vascular_invasion"] = True

        # Steatosis percent
        match = re.search(r"(\d+)\s*%", text)
        if match and hist_out["steatosis_percent"] is None:
            pct = int(match.group(1))
            hist_out["steatosis_percent"] = pct
            hist_out["steatosis_grade"] = self._calculate_steatosis_grade(pct)

    def _llm_extract_all(self, pathology_text, molecular_text, existing):
        """
        Single GPT-4o-mini call for histology + molecular extraction.
        No response_format (not supported).
        Enforces JSON via strict instructions + regex cleanup fallback.
        """

        extraction_prompt = f"""
    You are an expert in pathology & molecular extraction. 
    Extract ONLY explicitly stated values from the following texts.
    Return ONLY a JSON object.

    PATHOLOGY REPORT:
    {pathology_text}

    MOLECULAR REPORT:
    {molecular_text}

    Return JSON exactly in this format:

    {{
    "diagnosis": "string or null",
    "differentiation": "Well|Moderately differentiated|Poor|Undifferentiated|null",
    "fibrosis_stage": "F0|F1|F2|F3|F4|null",
    "steatosis_percent": number or null,
    "steatosis_grade": 0|1|2|3|null,
    "lobular_inflammation": 0|1|2|3|null,
    "ballooning": 0|1|2|null,
    "vascular_invasion": true|false|null,

    "TERT_promoter_mutation": "positive|negative|not_reported",
    "TP53_mutation": "positive|negative|not_reported",
    "CTNNB1_mutation": "positive|negative|not_reported",
    "MSI_status": "MSI-H|MSI-L|MSS|not_reported",
    "PDL1_IHC": "string or not_reported",
    "TMB": "string or not_reported",

    "notes": "extraction notes"
    }}

    Rules:
    - ONLY return JSON
    - If a value is not explicitly mentioned, return null or "not_reported"
    - Do NOT infer.
    """

        try:
            resp = self.client.responses.create(
                model=self.extract_model,
                input=[{"role": "user", "content": extraction_prompt}],
                temperature=0,
                max_output_tokens=500
            )

            raw = resp.output[0].content[0].text.strip()

            # --- Safety: extract JSON using regex ---
            json_match = re.search(r"\{[\s\S]*\}", raw)
            if not json_match:
                raise ValueError("No JSON found in LLM output")

            json_str = json_match.group(0)
            return json.loads(json_str)

        except Exception as e:
            print("Extraction error:", e)
            return {}


    # =================================================================
    #  MERGE EXTRACTED DATA
    # =================================================================
    def _merge_llm_extraction(self, summary, llm):
        if not llm:
            summary["histology"]["comments"] = "LLM extraction failed."
            return

        hist = summary["histology"]
        mol = summary["molecular_profile"]

        # Merge histology
        for key in ["diagnosis", "differentiation", "fibrosis_stage",
                    "steatosis_percent", "steatosis_grade",
                    "lobular_inflammation", "ballooning",
                    "vascular_invasion"]:
            if llm.get(key) is not None and hist.get(key) is None:
                hist[key] = llm[key]

        # Merge molecular
        for key in mol:
            if key in llm and llm[key] != "not_reported":
                mol[key] = llm[key]

        hist["comments"] = llm.get("notes", "LLM extraction applied.")

    # =================================================================
    #  INTERPRETATION (GPT-4o)
    # =================================================================
    def _generate_interpretation(self, summary):
        prompt = [{
            "role": "user",
            "content": f"""
Summarize pathology in 2–3 sentences for tumor board.
Avoid 'not_reported' markers.

{json.dumps(summary, indent=2)}
"""
        }]

        try:
            resp = self.client.responses.create(
                model=self.interpret_model,
                input=prompt,
                temperature=0.3,
                max_output_tokens=200,
            )
            return resp.output[0].content[0].text.strip()

        except Exception:
            return "Pathology summarized."

    # =================================================================
    #  CONFIDENCE
    # =================================================================
    def _calculate_confidence(self, summary, markers, p_text, m_text):
        conf = 0.5

        structured = sum(1 for k in ["differentiation","fibrosis_stage","vascular_invasion",
                                     "steatosis_percent","steatosis_grade"]
                         if markers.get(k) is not None)
        conf += structured * 0.08

        if p_text and len(p_text) > 80:
            conf += 0.1

        hist = summary["histology"]
        critical = ["diagnosis", "differentiation", "fibrosis_stage", "vascular_invasion"]
        present = sum(1 for k in critical if hist.get(k) is not None)
        conf += present * 0.05

        mol = summary["molecular_profile"]
        non_missing = sum(1 for v in mol.values() if v != "not_reported")
        conf += non_missing * 0.02

        return round(max(0.0, min(1.0, conf)), 2)


# =================================================================
#  USAGE EXAMPLE (FULLY UPDATED FOR GPT-4o-MINI)
# =================================================================

def main():
    agent = PathologyMolecularAgent(openai_api_key="YOUR_API_KEY_HERE")

    # ----------------- Example 1 -----------------
    sample_input_1 = {
        "pathology": {
            "biopsy_performed": True,
            "pathology_report_text": """
            Core needle biopsy of liver mass:
            Diagnosis: Hepatocellular carcinoma, moderately differentiated.
            Cirrhosis present (F4).
            Macrovesicular steatosis ~35%.
            No vascular invasion identified.
            balloning: 1
            """,
            "molecular_profile_text": """
            TERT promoter mutation detected.
            TP53 wild-type.
            CTNNB1 wild-type.
            MSI stable (MSS).
            PD-L1 CPS 3.
            TMB 2 muts/Mb.
            """,
            "files": {},
            "biopsy_markers": {
                "differentiation": "Moderate",
                "vascular_invasion": False,
                "steatosis_percent": 35,
                "lobular_inflammation": 1,
                "fibrosis_stage": "F4"
            }
        }
    }

    print("\n================= EXAMPLE 1 =================")
    result_1 = agent.process(sample_input_1)
    print(json.dumps(result_1, indent=2))

    # ----------------- Example 2 -----------------
    sample_input_2 = {
        "pathology": {
            "biopsy_performed": True,
            "pathology_report_text": """
            Moderately differentiated HCC.
            Bridging fibrosis present.
            Mild steatosis.
            No vascular invasion.
            """,
            "molecular_profile_text": "",
            "files": {},
            "biopsy_markers": {}
        }
    }

    print("\n================= EXAMPLE 2 =================")
    result_2 = agent.process(sample_input_2)
    print(json.dumps(result_2, indent=2))

    # ----------------- Example 3 -----------------
    sample_input_3 = {
        "pathology": {
            "biopsy_performed": False,
            "pathology_report_text": "",
            "molecular_profile_text": "",
            "files": {},
            "biopsy_markers": {}
        }
    }

    print("\n================= EXAMPLE 3 =================")
    result_3 = agent.process(sample_input_3)
    print(json.dumps(result_3, indent=2))


if __name__ == "__main__":
    main()
