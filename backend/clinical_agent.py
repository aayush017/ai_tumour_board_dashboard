"""
ClinicalDataAgent (updated)
- Baseline labs used for derived scores
- Lab flags include PT_sec (range loaded from parameters.xlsx if available)
- Ground truth block is passed through from input; if absent, agent returns null ground_truth block
"""

import json
import math
import re
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
import os
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Default lab reference ranges
DEFAULT_LAB_REFERENCE_RANGES = {
    "hemoglobin_g_dl": {"male": (13.0, 17.0), "female": (12.0, 15.0)},
    "WBC_k": (4.0, 10.0),
    "platelets_k": (150, 450),
    "total_bilirubin_mg_dl": (0.3, 1.2),
    "direct_bilirubin_mg_dl": (0.0, 0.3),
    "AST_U_L": (0, 40),
    "ALT_U_L": (0, 41),
    "ALP_U_L": (44, 147),
    "albumin_g_dl": (3.4, 5.0),
    "INR": (0.8, 1.2),
    "PT_sec": (11.0, 15.0),   # default; will be replaced by Excel if present
    "Na_mmol_L": (135, 146),
    "creatinine_mg_dl": {"male": (0.7, 1.3), "female": (0.6, 1.1)},
    "AFP_ng_ml": (0, 20),
    "CRP_mg_L": (0, 10)
}


class ClinicalDataAgent:
    def __init__(self, openai_api_key: Optional[str] = None, model: str = "gpt-4o"):
        """Initialize the Clinical Data Agent."""
        self.client = OpenAI(api_key=openai_api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.ULN_AST = 40.0
        # Load lab ranges (attempt to read XLSX)
        self.lab_ranges = DEFAULT_LAB_REFERENCE_RANGES.copy()

    # -----------------------
    # Public process function
    # -----------------------
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process clinical input and return:
        {
          "clinical_summary": {...},
          "agent_metadata": {...},
          "ground_truth": {"clinical_scores": {Child_Pugh, MELD, MELD_Na, ALBI}}
        }
        Ground truth is passed through if present; else nulls are returned.
        """
        clinical_summary = self._initialize_clinical_summary(input_data)
        demographics = input_data.get("demographics", {})

        # Extract from notes if available
        notes = input_data.get("clinical", {}).get("clinical_notes_text")
        if notes:
            extracted = self._extract_from_clinical_notes(notes)
            self._merge_extracted_into_summary(clinical_summary, extracted)

        # Compute derived scores using baseline labs only
        self._compute_derived_scores(clinical_summary, age=demographics.get("age"))

        # Compute lab flags (baseline only)
        clinical_summary["lab_flags"] = self._compute_lab_flags(clinical_summary["labs_baseline"], demographics)

        # Generate interpretation (LLM) referencing lab_flags
        clinical_summary["clinical_interpretation"] = self._generate_interpretation(clinical_summary, demographics)

        # Confidence
        confidence = self._calculate_confidence(clinical_summary, input_data)

        # Ground truth pass-through: if input has ground_truth -> copy exactly, else null block
        input_gt = input_data.get("ground_truth")
        if input_gt and isinstance(input_gt, dict):
            gt_out = input_gt
        else:
            gt_out = {
                "clinical_scores": {
                    "Child_Pugh": None,
                    "MELD": None,
                    "MELD_Na": None,
                    "ALBI": None
                }
            }

        return {
            "clinical_summary": clinical_summary,
            "agent_metadata": {"clinical_agent_confidence": round(confidence, 2)},
            "ground_truth": gt_out
        }

    # -----------------------
    # Helpers: initialization
    # -----------------------
    def _initialize_clinical_summary(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        clinical = input_data.get("clinical", {})
        lab_baseline = input_data.get("lab_data", {}).get("baseline", {}) or {}
        lab_time_series = input_data.get("lab_data", {}).get("time_series", []) or []

        normalized_baseline = self._normalize_labs(lab_baseline)
        normalized_series = [self._normalize_labs(x) for x in lab_time_series]

        return {
            "etiology": clinical.get("etiology", ""),
            "symptoms": clinical.get("symptoms", []) or [],
            "comorbidities": clinical.get("comorbidities", []) or [],
            "ascites": self._normalize_ascites(clinical.get("ascites")),
            "encephalopathy": self._normalize_encephalopathy(clinical.get("encephalopathy")),
            "ECOG": self._normalize_ecog(clinical.get("ECOG")),
            "labs_baseline": normalized_baseline,
            "labs_time_series": normalized_series,
            "derived_scores": {
                "Child_Pugh": {"score": None, "class": "", "components": {}},
                "MELD": None,
                "MELD_Na": None,
                "ALBI": {"score": None, "grade": None},
                "APRI": None,
                "FIB_4": None
            },
            "lab_flags": {},
            "clinical_interpretation": ""
        }

    def _normalize_ascites(self, ascites: Optional[Any]) -> Optional[str]:
        if ascites is None:
            return None
        s = str(ascites).strip().lower()
        if s in ("", "none", "absent", "no ascites"):
            return "none"
        if any(t in s for t in ("trace", "mild", "minimal")):
            return "mild"
        if "moderate" in s:
            return "moderate"
        if any(t in s for t in ("severe", "tense", "marked", "massive")):
            return "severe"
        return s

    def _normalize_encephalopathy(self, enceph: Optional[Any]) -> Optional[str]:
        if enceph is None:
            return None
        s = str(enceph).strip().lower()
        if s in ("", "none", "absent", "no encephalopathy"):
            return "none"
        if any(token in s for token in ("grade 1", "grade1", "mild")):
            return "grade1"
        if any(token in s for token in ("grade 2", "grade2", "moderate")):
            return "grade2"
        if any(token in s for token in ("grade 3", "grade3", "severe")):
            return "grade3"
        if any(token in s for token in ("grade 4", "grade4", "coma")):
            return "grade4"
        return s

    def _normalize_ecog(self, ecog: Optional[Any]) -> Optional[int]:
        if ecog is None:
            return None
        try:
            v = int(ecog)
            if 0 <= v <= 4:
                return v
        except Exception:
            pass
        s = str(ecog).lower()
        if "fully active" in s or "no restrictions" in s:
            return 0
        if "restricted" in s or "light work" in s:
            return 1
        return None

    def _normalize_labs(self, labs: Dict[str, Any]) -> Dict[str, Optional[float]]:
        normalized = {}
        lab_fields = [
            "hemoglobin_g_dl", "WBC_k", "platelets_k", "total_bilirubin_mg_dl",
            "direct_bilirubin_mg_dl", "AST_U_L", "ALT_U_L", "ALP_U_L",
            "albumin_g_dl", "INR", "PT_sec", "Na_mmol_L", "creatinine_mg_dl",
            "AFP_ng_ml", "CRP_mg_L"
        ]
        if isinstance(labs, dict) and "date" in labs:
            normalized["date"] = labs.get("date")
        for f in lab_fields:
            normalized[f] = self._to_float_or_none(labs.get(f)) if isinstance(labs, dict) else None
        return normalized

    def _to_float_or_none(self, value: Any) -> Optional[float]:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        try:
            return float(value)
        except Exception:
            s = str(value)
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            if m:
                try:
                    return float(m.group(0))
                except Exception:
                    return None
            return None

    # -----------------------
    # LLM extraction
    # -----------------------
    def _extract_from_clinical_notes(self, clinical_notes: str, max_retries: int = 2) -> Dict[str, Any]:
        prompt = f"""You are a hepatology-focused medical information extraction system. 
Extract the following structured fields from the clinical notes. 
Your job is to determine if ASCITES or ENCEPHALOPATHY and other fields is present, even if they are not named explicitly, by using clinical cues.

-----------------------------------
CLINICAL NOTES:
{clinical_notes}
-----------------------------------

EXTRACTION RULES (VERY IMPORTANT):

1. **Ascites Detection**
   Consider ascites PRESENT if ANY of the following are described:
   - “distended abdomen”, “abdominal distension”, “tense abdomen”
   - “shifting dullness”, “fluid thrill”, “fluid wave”
   - “free fluid”, “minimal free fluid”, “moderate ascites”, “massive ascites”
   - imaging notes like “ascites seen”, “peritoneal fluid”
   - +ve ascites on exam
   - if anything about ascites is mentiioned, even if vague then infer
   If present, classify as:
   - "mild" → trace, minimal, small volume, minimal free fluid
   - "moderate" → moderate, appreciable but not tense
   - "severe" → massive, large volume, tense ascites
   also infer classification based on descriptors above.
   If explicitly stated “no ascites” or exam findings indicating absence → "none".

2. **Encephalopathy Detection**
   Consider encephalopathy PRESENT if ANY of the following phrases appear:
   - “confused”, “disoriented”, “altered sensorium”, “drowsy”, “obtunded”
   - “asterixis”, “flapping tremor”
   - “slowed mentation”, “lethargic”, “irritable”
   - “hepatic fetor / foetor hepaticus”
   - “poor concentration”, “behavioral changes”

   Severity mapping:
   - "grade1": mild confusion, sleep disturbance, irritability, mild asterixis
   - "grade2": disorientation, lethargy, obvious asterixis, personality change
   - "grade3": somnolent, markedly confused, responds to pain
   - "grade4": coma, unresponsive

   If explicitly stated “no encephalopathy” or normal neuro exam or something similar → "none".

3. **ECOG**
   Accept explicit ECOG values. 
   Or infer if phrases indicate performance status or is similar to one of the following:
   - Fully active → ECOG 0
   - Light work / restricted strenuous activity → ECOG 1
   - Ambulatory >50% of day, but limited → ECOG 2
   - Bedbound >50% of day → ECOG 3
   - Completely disabled → ECOG 4

4. **Symptoms & Comorbidities**
   Extract only if explicitly mentioned.
   Do NOT invent symptoms.

5. Return ONLY JSON in this schema:

{{
  "ascites": "none" | "mild" | "moderate" | "severe" | null,
  "encephalopathy": "none" | "grade1" | "grade2" | "grade3" | "grade4" | null,
  "ECOG": 0 | 1 | 2 | 3 | 4 | null ,
  "etiology": "string or null",
  "symptoms": ["list"] or null,
  "comorbidities": ["list"] or null
}}

DONOT HALLUCINATE DATA."""
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a careful clinical extractor. Return only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=512
                )
                try:
                    text = response.choices[0].message.content
                except Exception:
                    try:
                        text = response.choices[0].text
                    except Exception:
                        text = str(response)
                json_text = self._extract_json_from_text(text)
                if not json_text:
                    raise ValueError("No JSON found in LLM response")
                parsed = json.loads(json_text)
                allowed_keys = {"ascites", "encephalopathy", "ECOG", "etiology", "symptoms", "comorbidities"}
                parsed = {k: parsed.get(k) for k in allowed_keys if k in parsed}
                return parsed
            except Exception as e:
                logger.warning(f"LLM extraction attempt {attempt+1} failed: {e}")
                time.sleep(0.5 * (attempt + 1))
                continue
        return {"ascites": None, "encephalopathy": None, "ECOG": None, "etiology": None, "symptoms": None, "comorbidities": None}

    def _extract_json_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = text[start: end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            depth = 0
            start_idx = None
            for i, ch in enumerate(text):
                if ch == "{":
                    if start_idx is None:
                        start_idx = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        candidate = text[start_idx: i + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except Exception:
                            start_idx = None
                            continue
            return None

    def _merge_extracted_into_summary(self, summary, extracted):
        """
        Safely merge LLM-extracted values into the structured summary.
        STRICT RULES:
        - Never overwrite clinician-entered data with a weaker/noisy LLM guess.
        - Only escalate severity for ascites/encephalopathy.
        - Accept LLM values ONLY if summary value is missing or less specific.
        """

        # -----------------------
        # Helper severity maps
        # -----------------------
        ASCITES_ORDER = {
            None: -1,
            "none": 0,
            "mild": 1,
            "moderate": 2,
            "severe": 3
        }

        ENCEPH_ORDER = {
            None: -1,
            "none": 0,
            "grade1": 1,
            "grade2": 2,
            "grade3": 3,
            "grade4": 4
        }

        # -----------------------
        # 1. ASCITES (escalation only)
        # -----------------------
        new = extracted.get("ascites")
        old = summary.get("ascites")

        if new is not None:
            # Reject LLM "none" if summary already has ANY level of ascites
            if new == "none" and old not in (None, "", "none"):
                pass  # keep old
            else:
                # Allow upgrade (none → mild, mild → moderate, etc.)
                if ASCITES_ORDER.get(new, -1) > ASCITES_ORDER.get(old, -1):
                    summary["ascites"] = new

        # -----------------------
        # 2. ENCEPHALOPATHY (escalation only)
        # -----------------------
        new = extracted.get("encephalopathy")
        old = summary.get("encephalopathy")

        if new is not None:
            if new == "none" and old not in (None, "", "none"):
                pass  # don't overwrite true encephalopathy
            else:
                if ENCEPH_ORDER.get(new, -1) > ENCEPH_ORDER.get(old, -1):
                    summary["encephalopathy"] = new

        # -----------------------
        # 3. ECOG (only fill missing)
        # -----------------------
        if summary.get("ECOG") is None and extracted.get("ECOG") is not None:
            try:
                summary["ECOG"] = int(extracted["ECOG"])
            except:
                pass

        # -----------------------
        # 4. Etiology (only if missing)
        # -----------------------
        if not summary.get("etiology") and extracted.get("etiology"):
            summary["etiology"] = extracted["etiology"]

        # -----------------------
        # 5. Symptoms (fill only if empty)
        # -----------------------
        new_sym = extracted.get("symptoms")
        if new_sym:
            if isinstance(new_sym, str):
                new_sym = [s.strip() for s in new_sym.split(",")]

            if not summary.get("symptoms"):
                summary["symptoms"] = new_sym

        # -----------------------
        # 6. Comorbidities
        # -----------------------
        new_com = extracted.get("comorbidities")
        if new_com:
            if isinstance(new_com, str):
                new_com = [s.strip() for s in new_com.split(",")]

            if not summary.get("comorbidities"):
                summary["comorbidities"] = new_com

    # -----------------------
    # Derived scores (baseline)
    # -----------------------
    def _compute_derived_scores(self, clinical_summary: Dict[str, Any], age: Optional[int] = None):
        labs = clinical_summary.get("labs_baseline", {})

        cp = self._compute_child_pugh(
            bilirubin=labs.get("total_bilirubin_mg_dl"),
            albumin=labs.get("albumin_g_dl"),
            inr=labs.get("INR"),
            ascites=clinical_summary.get("ascites"),
            encephalopathy=clinical_summary.get("encephalopathy")
        )
        clinical_summary["derived_scores"]["Child_Pugh"] = cp

        meld = self._compute_meld(
            bilirubin=labs.get("total_bilirubin_mg_dl"),
            inr=labs.get("INR"),
            creatinine=labs.get("creatinine_mg_dl")
        )
        clinical_summary["derived_scores"]["MELD"] = meld

        meld_na = self._compute_meld_na(meld=meld, sodium=labs.get("Na_mmol_L"))
        clinical_summary["derived_scores"]["MELD_Na"] = meld_na

        clinical_summary["derived_scores"]["ALBI"] = self._compute_albi(
            bilirubin_mg_dl=labs.get("total_bilirubin_mg_dl"),
            albumin_g_dl=labs.get("albumin_g_dl")
        )

        clinical_summary["derived_scores"]["APRI"] = self._compute_apri(
            ast=labs.get("AST_U_L"),
            platelets_k=labs.get("platelets_k"),
            uln_ast=self.ULN_AST
        )

        clinical_summary["derived_scores"]["FIB_4"] = self._compute_fib4(
            age=age,
            ast=labs.get("AST_U_L"),
            alt=labs.get("ALT_U_L"),
            platelets_k=labs.get("platelets_k")
        )

    def _compute_child_pugh(self, bilirubin, albumin, inr, ascites, encephalopathy) -> Dict[str, Any]:
        components = {"bilirubin": None, "albumin": None, "INR": None, "ascites": None, "encephalopathy": None}
        score = 0

        if bilirubin is not None:
            if bilirubin < 2.0:
                components["bilirubin"] = 1
            elif bilirubin <= 3.0:
                components["bilirubin"] = 2
            else:
                components["bilirubin"] = 3
            score += components["bilirubin"]

        if albumin is not None:
            if albumin > 3.5:
                components["albumin"] = 1
            elif albumin >= 2.8:
                components["albumin"] = 2
            else:
                components["albumin"] = 3
            score += components["albumin"]

        if inr is not None:
            if inr < 1.7:
                components["INR"] = 1
            elif inr <= 2.3:
                components["INR"] = 2
            else:
                components["INR"] = 3
            score += components["INR"]

        if ascites is not None:
            ascites_map = {"none": 1, "mild": 2, "moderate": 3, "severe": 3}
            components["ascites"] = ascites_map.get(ascites, None)
            if components["ascites"] is not None:
                score += components["ascites"]

        if encephalopathy is not None:
            enceph_map = {"none": 1, "grade1": 2, "grade2": 2, "grade3": 3, "grade4": 3}
            components["encephalopathy"] = enceph_map.get(encephalopathy, None)
            if components["encephalopathy"] is not None:
                score += components["encephalopathy"]

        if any(v is None for v in components.values()):
            return {"score": None, "class": "", "components": components}
        else:
            if score <= 6:
                child_class = "A"
            elif score <= 9:
                child_class = "B"
            else:
                child_class = "C"
            return {"score": int(score), "class": child_class, "components": components}

    def _compute_meld(self, bilirubin, inr, creatinine) -> Optional[int]:
        if any(x is None for x in [bilirubin, inr, creatinine]):
            return None
        try:
            bili = max(float(bilirubin), 1.0)
            inr_v = max(float(inr), 1.0)
            creat = max(float(creatinine), 1.0)
            meld = (3.78 * math.log(bili) + 11.2 * math.log(inr_v) + 9.57 * math.log(creat) + 6.43)
            meld = round(meld)
            meld = int(max(6, min(40, meld)))
            return meld
        except Exception:
            return None

    def _compute_meld_na(self, meld, sodium) -> Optional[int]:
        if meld is None or sodium is None:
            return None
        try:
            na = float(sodium)
            na = max(125.0, min(140.0, na))
            meld_na = meld + 1.59 * (135.0 - na)
            meld_na = int(max(6, min(40, round(meld_na))))
            return meld_na
        except Exception:
            return None

    def _compute_albi(self, bilirubin_mg_dl: Optional[float], albumin_g_dl: Optional[float]) -> Dict[str, Any]:
        if bilirubin_mg_dl is None or albumin_g_dl is None:
            return {"score": None, "grade": None}
        try:
            bili_umol_per_l = bilirubin_mg_dl * 17.1
            albumin_g_per_l = albumin_g_dl * 10.0
            albi_score = (math.log10(bili_umol_per_l) * 0.66) + (albumin_g_per_l * -0.085)
            albi_score = round(albi_score, 3)
            if albi_score <= -2.60:
                grade = 1
            elif albi_score <= -1.39:
                grade = 2
            else:
                grade = 3
            return {"score": albi_score, "grade": grade}
        except Exception:
            return {"score": None, "grade": None}

    def _compute_apri(self, ast: Optional[float], platelets_k: Optional[float], uln_ast: float = None) -> Optional[float]:
        if ast is None or platelets_k is None:
            return None
        try:
            uln = uln_ast if uln_ast is not None else self.ULN_AST
            if platelets_k == 0:
                return None
            apri = ((ast / float(uln)) / float(platelets_k)) * 100.0
            return round(apri, 2)
        except Exception:
            return None

    def _compute_fib4(self, age: Optional[int], ast: Optional[float], alt: Optional[float], platelets_k: Optional[float]) -> Optional[float]:
        if any(v is None for v in [age, ast, alt, platelets_k]):
            return None
        try:
            if platelets_k == 0 or alt == 0:
                return None
            fib4 = (float(age) * float(ast)) / (float(platelets_k) * math.sqrt(float(alt)))
            return round(fib4, 2)
        except Exception:
            return None

    # -----------------------
    # Lab flags
    # -----------------------
    def _compute_lab_flags(self, baseline_labs: Dict[str, Optional[float]], demographics: Dict[str, Any]) -> Dict[str, Optional[str]]:
        flags = {}
        sex = (demographics.get("sex") or "").lower()
        for lab_key in [
            "hemoglobin_g_dl", "WBC_k", "platelets_k", "total_bilirubin_mg_dl",
            "direct_bilirubin_mg_dl", "AST_U_L", "ALT_U_L", "ALP_U_L",
            "albumin_g_dl", "INR", "PT_sec", "Na_mmol_L", "creatinine_mg_dl", "AFP_ng_ml", "CRP_mg_L"
        ]:
            val = baseline_labs.get(lab_key)
            if val is None:
                flags[lab_key] = None
                continue
            ref = self.lab_ranges.get(lab_key)
            if isinstance(ref, dict):
                # sex-specific: male/female fallback
                ref_range = ref.get(sex) if isinstance(ref.get(sex), (list, tuple)) else None
                if ref_range is None:
                    # fallback to any numeric pair in dict
                    for v in ref.values():
                        if isinstance(v, (list, tuple)) and len(v) == 2:
                            ref_range = v
                            break
            else:
                ref_range = ref
            if not ref_range or not isinstance(ref_range, (list, tuple)) or len(ref_range) != 2:
                flags[lab_key] = None
                continue
            low, high = ref_range
            try:
                v = float(val)
                if v < float(low):
                    flags[lab_key] = "low"
                elif v > float(high):
                    flags[lab_key] = "high"
                else:
                    flags[lab_key] = "normal"
            except Exception:
                flags[lab_key] = None
        return flags

    # -----------------------
    # Interpretation (LLM)
    # -----------------------
#     def _generate_interpretation(self, clinical_summary: Dict[str, Any], demographics: Dict[str, Any], max_retries: int = 2) -> str:
#         child = clinical_summary.get("derived_scores", {}).get("Child_Pugh", {})
#         child_class = child.get("class") or "Unknown"
#         child_score = child.get("score")
#         meld_na = clinical_summary.get("derived_scores", {}).get("MELD_Na")
#         ecog = clinical_summary.get("ECOG")
#         afp = clinical_summary.get("labs_baseline", {}).get("AFP_ng_ml")
#         etiology = clinical_summary.get("etiology") or "Unknown"
#         symptoms = ", ".join(clinical_summary.get("symptoms") or [])
#         labs_ts = "Available" if clinical_summary.get("labs_time_series") else "Not available"

#         lab_flags = clinical_summary.get("lab_flags", {})
#         abnormal_list = []
#         for k, v in lab_flags.items():
#             if v in ("low", "high"):
#                 pretty = k.replace("_", " ").replace("mg dl", "mg/dL").replace("mmol l", "mmol/L")
#                 abnormal_list.append(f"{pretty} ({v})")
#         abnormal_text = "; ".join(abnormal_list) if abnormal_list else "no major baseline laboratory abnormalities"

#         prompt = f"""You are a hepatology expert. Create a concise 2-4 sentence clinical interpretation for an HCC patient.
# Do NOT include radiology or pathology statements.

# Etiology: {etiology}
# Child-Pugh: {child_class} (score: {child_score})
# MELD-Na: {meld_na}
# ECOG: {ecog}
# AFP: {afp}
# Ascites: {clinical_summary.get('ascites')}
# Encephalopathy: {clinical_summary.get('encephalopathy')}
# Symptoms: {symptoms}
# Lab time-series: {labs_ts}

# Baseline lab abnormalities: {abnormal_text}

# Write 2-4 clinical sentences focused on:
# - cirrhosis severity & etiology
# - liver function (Child-Pugh & MELD)
# - performance status
# - notable AFP comment (if present)
# - mention the most relevant baseline lab abnormalities in one short clause
# """
#         for attempt in range(max_retries):
#             try:
#                 response = self.client.chat.completions.create(
#                     model=self.model,
#                     messages=[
#                         {"role": "system", "content": "You are a hepatology specialist. Be concise and clinical."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=0.25,
#                     max_tokens=220
#                 )
#                 try:
#                     text = response.choices[0].message.content
#                 except Exception:
#                     try:
#                         text = response.choices[0].text
#                     except Exception:
#                         text = str(response)
#                 interpretation = str(text).strip()
#                 if interpretation:
#                     return interpretation[:1000]
#             except Exception as e:
#                 logger.warning(f"Interpretation LLM attempt {attempt+1} failed: {e}")
#                 time.sleep(0.5 * (attempt + 1))
#                 continue
#         return f"Patient with {etiology} (Child-Pugh {child_class}, MELD-Na {meld_na}) and ECOG {ecog}. Baseline labs: {abnormal_text}."


    def _generate_interpretation(self, clinical_summary: Dict[str, Any], demographics: Dict[str, Any], max_retries: int = 3) -> str:
        """Generate interpretation + safe descriptive-only trend summary."""
        child = clinical_summary.get("derived_scores", {}).get("Child_Pugh", {})
        child_class = child.get("class") or "Unknown"
        child_score = child.get("score")
        meld_na = clinical_summary.get("derived_scores", {}).get("MELD_Na")
        ecog = clinical_summary.get("ECOG")
        afp = clinical_summary.get("labs_baseline", {}).get("AFP_ng_ml")
        etiology = clinical_summary.get("etiology") or "Unknown"
        symptoms = ", ".join(clinical_summary.get("symptoms") or [])

        # -------------------------------
        # SAFE, DESCRIPTIVE-ONLY TREND SUMMARY
        # -------------------------------
        trend_summary = ""
        ts = clinical_summary.get("labs_time_series", [])

        if ts and len(ts) > 0:
            latest = ts[-1]
            baseline = clinical_summary.get("labs_baseline", {})

            trend_items = []
            trend_fields = [
                "total_bilirubin_mg_dl", "albumin_g_dl", "INR", "AST_U_L", "ALT_U_L",
                "platelets_k", "Na_mmol_L", "creatinine_mg_dl", "AFP_ng_ml"
            ]

            for f in trend_fields:
                b = baseline.get(f)
                l = latest.get(f)
                if b is not None and l is not None:
                    if l > b:
                        trend_items.append(f"{f} increased")
                    elif l < b:
                        trend_items.append(f"{f} decreased")

            if trend_items:
                trend_summary = (
                    "Follow-up labs compared to baseline show: "
                    + "; ".join(trend_items)
                    + ". These follow-up values may be post-treatment; trends are described only and not interpreted clinically."
                )
            else:
                trend_summary = (
                    "Follow-up labs available, with changes noted but without consistent directional trends. "
                    "These may be post-treatment values and are described but not clinically interpreted."
                )
        else:
            trend_summary = "No follow-up lab data available."

        # -------------------------------
        # BASELINE CLINICAL INTERPRETATION PROMPT
        # -------------------------------
        lab_flags = clinical_summary.get("lab_flags", {})
        abnormal_list = []
        for k, v in lab_flags.items():
            if v in ("low", "high"):
                pretty = k.replace("_", " ").replace("mg dl", "mg/dL").replace("mmol l", "mmol/L")
                abnormal_list.append(f"{pretty} ({v})")
        abnormal_text = "; ".join(abnormal_list) if abnormal_list else "no major baseline laboratory abnormalities"

        prompt = f"""
    You are a hepatology expert. Create a concise 2–4 sentence clinical interpretation for an HCC patient.

    **Important:**
    - Interpret ONLY baseline clinical status.
    - DO NOT clinically interpret trends because follow-up labs may be post-treatment.
    - A separate trend-summary will be appended by the system.

    Etiology: {etiology}
    Child-Pugh: {child_class} (score: {child_score})
    MELD-Na: {meld_na}
    ECOG: {ecog}
    AFP: {afp}
    Ascites: {clinical_summary.get('ascites')}
    Encephalopathy: {clinical_summary.get('encephalopathy')}
    Symptoms: {symptoms}

    Baseline abnormalities: {abnormal_text}
    
    Write 2-4 clinical sentences focused on:
    - cirrhosis severity & etiology
    - liver function (Child-Pugh & MELD)
    - performance status
    - notable AFP comment (if present)
    - mention the most relevant baseline lab abnormalities in one short clause
    """

        # -------------------------------
        # CALL LLM FOR BASELINE INTERPRETATION ONLY
        # -------------------------------
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a hepatology specialist. Be concise and clinical. Do NOT interpret lab trends."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.25,
                    max_tokens=220
                )
                try:
                    text = response.choices[0].message.content
                except Exception:
                    try:
                        text = response.choices[0].text
                    except Exception:
                        text = str(response)

                interpretation = str(text).strip()
                if interpretation:
                    # Append safe trend summary BELOW the interpretation.
                    return interpretation[:1000] + "\n\n" + trend_summary

            except Exception:
                time.sleep(0.5)
                continue

        # Fallback
        return f"Patient with {etiology} (Child-Pugh {child_class}, MELD-Na {meld_na}) and ECOG {ecog}. Baseline labs: {abnormal_text}.\n\n{trend_summary}"


    # -----------------------
    # Confidence
    # -----------------------
    def _calculate_confidence(self, clinical_summary: Dict[str, Any], input_data: Dict[str, Any]) -> float:
        fields = [
            clinical_summary.get("etiology"),
            clinical_summary.get("ascites"),
            clinical_summary.get("encephalopathy"),
            clinical_summary.get("ECOG")
        ]
        labs = clinical_summary.get("labs_baseline", {})
        lab_fields = ["total_bilirubin_mg_dl", "albumin_g_dl", "INR", "creatinine_mg_dl", "Na_mmol_L",
                      "platelets_k", "AST_U_L", "ALT_U_L", "AFP_ng_ml"]

        total = len(fields) + len(lab_fields) + 3
        present = sum(1 for f in fields if f not in (None, "")) + sum(1 for lf in lab_fields if labs.get(lf) is not None)

        derived = clinical_summary.get("derived_scores", {})
        present += 1 if derived.get("Child_Pugh", {}).get("score") is not None else 0
        present += 1 if derived.get("MELD") is not None else 0
        present += 1 if derived.get("ALBI", {}).get("score") is not None else 0

        if total == 0:
            return 0.0
        base_conf = present / total
        if clinical_summary.get("labs_time_series"):
            base_conf = min(1.0, base_conf + 0.05)
        return round(base_conf, 4)

# -----------------------
# Usage example 
# -----------------------
if __name__ == "__main__":
    from dotenv import load_dotenv
    import os

    load_dotenv()  # load .env file if present
    api_key = os.getenv("OPENAI_API_KEY")

    sample_input = {
        "demographics": {"name": "John Doe", "age": 76, "sex": "M", "BMI": 22.4},
        "clinical": {
            "etiology": "HCV-related cirrhosis",
            "symptoms": ["Pain", "Weight loss"],
            "comorbidities": ["Diabetes mellitus", "Hypertension"],
            "ascites": "",
            "encephalopathy": "",
            "ECOG": None,
            "clinical_notes_text": """
            Patient is a 76-year-old male with hepatitis C-related cirrhosis.
            He presents with right upper quadrant pain and unintentional weight loss.
            there is no evidence of ascites on physical exam. Patient is alert and oriented,
            there are no signs of hepatic encephalopathy. Patient is ambulatory and capable 
            of light work.
            """
        },
        "lab_data": {
            "baseline": {
                "hemoglobin_g_dl": 11.3,
                "WBC_k": 7.7,
                "platelets_k": 157,
                "total_bilirubin_mg_dl": 2.0,
                "direct_bilirubin_mg_dl": 1.29,
                "AST_U_L": 123,
                "ALT_U_L": 51.3,
                "ALP_U_L": 229,
                "albumin_g_dl": 3.75,
                "INR": 1.18,
                "PT_sec": 14.0,
                "Na_mmol_L": 126,
                "creatinine_mg_dl": 0.87,
                "AFP_ng_ml": 400000,
                "CRP_mg_L": 112
            },
            "time_series": [
                {
                    "date": "2025-02-01",
                    "hemoglobin_g_dl": 12.4,
                    "WBC_k": 8.6,
                    "platelets_k": 166,
                    "total_bilirubin_mg_dl": 2.2,
                    "direct_bilirubin_mg_dl": 1.8,
                    "AST_U_L": 67,
                    "ALT_U_L": 56,
                    "ALP_U_L": 178,
                    "albumin_g_dl": 3.8,
                    "INR": 1.30,
                    "PT_sec": 13.8,
                    "Na_mmol_L": 132,
                    "creatinine_mg_dl": 0.93,
                    "AFP_ng_ml": 3600,
                    "CRP_mg_L": 68
                }
            ]
        },
        # Example ground_truth present in input (agent should pass through unchanged)
        # "ground_truth": {"clinical_scores": {"Child_Pugh": "A", "MELD": 12, "MELD_Na": 12, "ALBI": "-2.6"}}
    }

    # Ensure OPENAI_API_KEY set in env or pass here
    agent = ClinicalDataAgent(openai_api_key=api_key, model="gpt-4o")
    output = agent.process(sample_input)
    print(json.dumps(output, indent=2))