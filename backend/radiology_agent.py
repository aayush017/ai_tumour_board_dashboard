import json
import re
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from openai import OpenAI


class OpenAILLM:
    """
    Enhanced LLM client with improved extraction prompts for radiology.
    """

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def extract(self, prompt: str) -> Dict[str, Any]:
        """
        Calls GPT-4o with improved system prompt for radiology extraction.
        """

        system_prompt = """You are an expert radiologist and medical information extraction AI.
Your task is to extract ONLY explicitly stated information from radiology reports.

CRITICAL RULES:
1. **DO NOT INFER OR ASSUME** - extract only what is explicitly written
2. If a feature is not mentioned → return None
3. If explicitly negated ("no", "absent", "negative", "without") → return false
4. If affirmed ("present", "demonstrates", "shows", "consistent with", "seen", "noted") → return True

EXTRACTION FIELDS:

{
   "arterial_phase_hyperenhancement": True/false/None,
   "washout": True/false/None,
   "enhancing_capsule": True/false/None,
   "threshold_growth": True/false/None,
   "pvtt": True/false/None,
   "extrahepatic_metastasis": True/false/None,
   "treated": True/false/None,
   "size_longest_cm": number/None,
   "size_transverse_cm": number/None,
   "li_rads_category": string/None
}

SPECIFIC EXTRACTION GUIDANCE:

**Enhancement Features:**
- "arterial_phase_hyperenhancement" (APHE): 
  * Look for: "arterial phase enhancement", "arterial phase hyperenhancement", "arterial enhancement", "APHE", "hypervascular", "hyperenhancing"
  * True if any of these present
  * For TREATED lesions: "viable enhancing tumor", "residual enhancement", "nodular enhancement", "viable tumor" → True
  * For TREATED lesions: "non-enhancing", "no enhancement", "treated area without enhancement" → FALSE

- "washout": 
  * Look for: "washout", "delayed phase hypoenhancement", "venous washout", "portal venous washout"
  * True if present

- "enhancing_capsule": 
  * Look for: "capsule", "enhancing capsule", "pseudocapsule"
  * True if present

- "threshold_growth":
  * Look for: explicit mention of growth, size increase, or interval enlargement
  * True if mentioned

**Size Extraction:**
- Extract from patterns like: "4.5 cm", "4.5 × 3.1 cm", "4.5 x 3.1 cm", "measuring 4.5 cm", "45 mm"
- Convert mm to cm (divide by 10)
- "residual tumor" or "residual enhancement" with size → extract that size
- If size mentioned but not a clear number → return None

**Treatment Status:**
- "treated": True if report mentions: "post-treatment", "post-TACE", "post-ablation", "treated lesion", "after therapy", "following treatment", "status post"
- "treated": FALSE if report is clearly baseline/pre-treatment or mentions "untreated", "treatment-naive"
- "treated": None if unclear from report

**LI-RADS Category:**
- Extract ONLY if explicitly stated
- Look for: "LR-5", "LR-4", "LR-3", "LR-TR Viable", "LR-TR Nonviable", "LR-TR-Viable", "LR-TR-Nonviable", "LI-RADS LR-5", "Classified as LR-5"
- Return the category as written (will be normalized later)
- Include variations like "LI-RADS LR-5" → extract "LR-5"

**PVTT and Metastasis:**
- Portal vein tumor thrombus (PVTT): "portal vein thrombosis", "portal vein tumor thrombus", "PVTT", "tumor thrombus"
- If "no portal vein tumor thrombus" or similar negation → FALSE
- Metastasis: "metastasis", "metastatic disease", "extrahepatic spread", "metastatic lesions"
- If "no metastasis" or similar negation → FALSE

**CRITICAL:** 
- Be VERY careful with negations: "no washout" → false, "washout present" → True
- Extract measurements precisely
- Return ONLY valid JSON, no explanations, no markdown, no extra text

OUTPUT: Return ONLY valid JSON with the exact keys above."""

        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract features from this radiology report:\n\n{prompt}"}
                ],
                temperature=0.0,
                max_tokens=500
            )

            raw = completion.choices[0].message.content

            # Attempt to parse the JSON returned
            try:
                return json.loads(raw)
            except:
                # Attempt best-effort JSON recovery
                try:
                    # Remove markdown code blocks if present
                    cleaned = raw.replace("```json", "").replace("```", "")
                    # Find JSON object
                    start = cleaned.find("{")
                    end = cleaned.rfind("}") + 1
                    if start >= 0 and end > start:
                        json_str = cleaned[start:end]
                        return json.loads(json_str)
                except:
                    pass
                
                return self._empty_extraction()
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return self._empty_extraction()

    def _empty_extraction(self):
        """Return empty extraction result"""
        return {
            "arterial_phase_hyperenhancement": None,
            "washout": None,
            "enhancing_capsule": None,
            "threshold_growth": None,
            "pvtt": None,
            "extrahepatic_metastasis": None,
            "treated": None,
            "size_longest_cm": None,
            "size_transverse_cm": None,
            "li_rads_category": None
        }


@dataclass
class RadiologyAgent:
    llm: Any
    assign_missing_ids: bool = True

    def _normalize_li_rads(self, li_rads_str):
        """Normalize various LI-RADS formats to standard format"""
        if not li_rads_str:
            return None
        
        s = str(li_rads_str).strip()
        
        # Remove common prefixes
        s = s.replace("LI-RADS ", "").replace("LIRADS ", "")
        
        # Normalize spacing/hyphens
        s = s.replace(" ", "-").replace("_", "-")
        s = s.upper()
        
        # Common variations
        if "LR-TR-VIABLE" in s or "LRTRVIABLE" in s or "TR-VIABLE" in s:
            return "LR-TR-Viable"
        if "LR-TR-NONVIABLE" in s or "LRTRNONVIABLE" in s or "TR-NONVIABLE" in s:
            return "LR-TR-Nonviable"
        if "LR-5" in s or "LR5" in s:
            return "LR-5"
        if "LR-4" in s or "LR4" in s:
            return "LR-4"
        if "LR-3" in s or "LR3" in s:
            return "LR-3"
        if "LR-2" in s or "LR2" in s:
            return "LR-2"
        if "LR-1" in s or "LR1" in s:
            return "LR-1"
        
        return s

    def _compute_confidence(self, studies):
        """
        Computes confidence (0.0–1.0) based on extraction completeness.
        Weighted system:
            - Enhancement extraction: 0.4
            - LI-RADS clarity: 0.3
            - Size extraction: 0.2
            - PVTT/mets extraction: 0.1
        """
        if not studies:
            return 0.0

        enh_score = 0
        lirads_score = 0
        size_score = 0
        metastasis_score = 0
        count = 0

        for study in studies:
            for lesion in study["lesions"]:
                count += 1

                ef = lesion["enhancement_features"]

                # Enhancement extraction completeness
                if (ef["arterial_phase_hyperenhancement"] is not None or 
                    ef["washout"] is not None):
                    enh_score += 1

                # LI-RADS clarity (Check Derived)
                lr = lesion.get("derived_li_rads")
                if lr and not lr.startswith("INSUFFICIENT_DATA"):
                    if lr in ["LR-5", "LR-4", "LR-TR-Viable", "LR-TR-Nonviable"]:
                        lirads_score += 1
                    elif lr == "LR-3":
                        lirads_score += 0.6

                # Size extracted?
                if lesion["size_cm"]["longest_diameter_cm"] is not None:
                    size_score += 1

                # PVTT + metastasis
                if lesion.get("pvtt") is not None:
                    metastasis_score += 0.5
                if lesion.get("extrahepatic_metastasis") is not None:
                    metastasis_score += 0.5

        if count == 0:
            return 0.0

        # Normalize
        enh_conf = enh_score / count
        lirads_conf = lirads_score / count
        size_conf = size_score / count
        meta_conf = metastasis_score / count

        # Weighted total
        score = (
            0.4 * enh_conf +
            0.3 * lirads_conf +
            0.2 * size_conf +
            0.1 * meta_conf
        )

        return round(score, 2)

    def process(self, radiology_section: Dict[str, Any]) -> Dict[str, Any]:
        studies_in = radiology_section.get("studies", [])
        processed_studies = []

        for si, study in enumerate(studies_in):
            proc = self._process_study(study, si)
            processed_studies.append(proc)

        temporal = self._compute_temporal_response(processed_studies)
        tumor_burden = self._compute_tumor_burden(
            processed_studies[0] if processed_studies else None
        )
        interpretation = self._build_interpretation(processed_studies, temporal)
        confidence = self._compute_confidence(processed_studies)

        return {
            "radiology_summary": {
                "studies": processed_studies,
                "temporal_response": temporal,
                "tumor_burden": tumor_burden,
                "radiology_interpretation": interpretation,
                "agent_metadata": {
                    "radiology_agent_confidence": confidence
                }
            }
        }

    def _process_study(self, study, study_index):
        date = study.get("date")
        modality = study.get("modality")
        report_text = study.get("radiology_report_text", "") or ""
        lesions_in = study.get("lesions", []) or []
        processed_lesions = []

        is_baseline = (study_index == 0)

        # If no lesions given → try extract from GPT-4o
        if not lesions_in:
            llm_out = self.llm.extract(report_text)
            
            if llm_out.get("size_longest_cm") is not None or llm_out.get("arterial_phase_hyperenhancement") is not None:
                lesion_obj = {
                    "lesion_id": "L1",
                    "segment": None,
                    "size_cm": {
                        "longest_diameter_cm": llm_out["size_longest_cm"],
                        "transverse_cm": llm_out["size_transverse_cm"],
                    },
                    "enhancement_features": {
                        "arterial_phase_hyperenhancement": llm_out["arterial_phase_hyperenhancement"],
                        "washout": llm_out["washout"],
                        "enhancing_capsule": llm_out["enhancing_capsule"],
                        "threshold_growth": llm_out["threshold_growth"],
                    },
                    "ground_truth_li_rads": self._normalize_li_rads(llm_out.get("li_rads_category")),
                    "derived_li_rads": None,
                    "pvtt": llm_out["pvtt"],
                    "extrahepatic_metastasis": llm_out["extrahepatic_metastasis"],
                    "treated": llm_out["treated"] if llm_out["treated"] is not None else (False if is_baseline else None),
                }
                lesion_obj["derived_li_rads"] = self._assign_li_rads(lesion_obj)
                processed_lesions.append(lesion_obj)
        else:
            # Structured lesions → Do GLOBAL extraction first (don't confuse LLM with lesion-specific prompts)
            
            # STEP 1: Extract from entire report globally
            global_llm_out = self.llm.extract(report_text)
            global_llm_out = self._validate_extraction(global_llm_out, report_text)
            
            # STEP 2: For each structured lesion, merge data
            for lesion_idx, lesion in enumerate(lesions_in):
                lesion_id = lesion.get("lesion_id") or f"L{lesion_idx + 1}"
                segment = lesion.get("segment")
                size = lesion.get("size_cm", {})
                longest = size.get("longest_diameter_cm") if isinstance(size, dict) else None
                transverse = size.get("transverse_cm") if isinstance(size, dict) else None

                # Use global extraction results (most reports describe lesions generally)
                llm_out = global_llm_out

                # Merge sizes: prefer input data, supplement with LLM extraction
                if longest is None and llm_out["size_longest_cm"] is not None:
                    longest = llm_out["size_longest_cm"]
                if transverse is None and llm_out["size_transverse_cm"] is not None:
                    transverse = llm_out["size_transverse_cm"]

                # Determine treatment status with logic
                treated_status = lesion.get("treated")
                if treated_status is None:
                    treated_status = llm_out["treated"]
                if treated_status is None:
                    # Heuristic: check modality for treatment keywords
                    modality_lower = (modality or "").lower()
                    if any(word in modality_lower for word in ["post-", "follow-up", "response"]):
                        treated_status = True
                    elif is_baseline:
                        treated_status = False

                # Ground truth LI-RADS: prefer input, then LLM extraction
                ground_truth_lr = lesion.get("li_rads")
                if not ground_truth_lr:
                    ground_truth_lr = llm_out.get("li_rads_category")
                ground_truth_lr = self._normalize_li_rads(ground_truth_lr)

                lesion_obj = {
                    "lesion_id": lesion_id,
                    "segment": segment,
                    "size_cm": {
                        "longest_diameter_cm": longest,
                        "transverse_cm": transverse,
                    },
                    "enhancement_features": {
                        "arterial_phase_hyperenhancement": llm_out["arterial_phase_hyperenhancement"],
                        "washout": llm_out["washout"],
                        "enhancing_capsule": llm_out["enhancing_capsule"],
                        "threshold_growth": llm_out["threshold_growth"],
                    },
                    "ground_truth_li_rads": ground_truth_lr,
                    "derived_li_rads": None,
                    "pvtt": lesion.get("pvtt") if lesion.get("pvtt") is not None else llm_out["pvtt"],
                    "extrahepatic_metastasis": lesion.get("extrahepatic_metastasis") if lesion.get("extrahepatic_metastasis") is not None else llm_out["extrahepatic_metastasis"],
                    "treated": treated_status,
                }
                lesion_obj["derived_li_rads"] = self._assign_li_rads(lesion_obj)
                processed_lesions.append(lesion_obj)

        # Compute overall LI-RADS for the study
        overall_li = self._compute_overall_li_rads(processed_lesions)
        cleaned_report = report_text.strip()

        return {
            "date": date,
            "modality": modality,
            "lesions": processed_lesions,
            "radiology_report_text": cleaned_report,
            "overall_derived_li_rads": overall_li,
        }

    def _assign_li_rads(self, lesion):
        """
        Calculates LI-RADS with EXPLICIT insufficient data handling.
        Returns descriptive strings when data is missing instead of generic "LR-NC".
        
        Format for insufficient data: "INSUFFICIENT_DATA: <reason>"
        This keeps JSON structure but informs user of the issue.
        """
        ef = lesion["enhancement_features"]
        aphe = ef.get("arterial_phase_hyperenhancement")
        washout = ef.get("washout")
        capsule = ef.get("enhancing_capsule")
        growth = ef.get("threshold_growth")
        
        treated = lesion["treated"]
        size_cm = lesion["size_cm"]["longest_diameter_cm"]

        # --- CRITICAL: Check for missing essential data ---
        
        # If treatment status unknown, we can't determine LR-TR vs LR
        if treated is None:
            return "INSUFFICIENT_DATA: treatment_status_unknown"
        
        # --- TREATED LESIONS (LR-TR) ---
        if treated:
            # For treated lesions, size is less critical but enhancement is key
            if aphe is None and washout is None:
                return "INSUFFICIENT_DATA: enhancement_data_missing_for_treated_lesion"
            
            # Viable if nodular APHE or Washout
            if aphe or washout:
                return "LR-TR-Viable"
            return "LR-TR-Nonviable"

        # --- UNTREATED LESIONS ---
        
        # Size is critical for untreated lesion classification
        if size_cm is None:
            return "INSUFFICIENT_DATA: size_missing_for_untreated_lesion"
        
        # For untreated lesions, we need at least some enhancement data
        if all(v is None for v in [aphe, washout, capsule, growth]):
            return "INSUFFICIENT_DATA: no_enhancement_features_available"
        
        size_mm = size_cm * 10

        # Size-based classification
        if size_mm < 10:
            return "LR-3"

        # Intermediate size (10 - 19mm)
        if 10 <= size_mm < 20:
            if aphe is None:
                # Can't determine without APHE status
                return "INSUFFICIENT_DATA: APHE_status_unknown_for_10-19mm_lesion"
            
            if aphe:
                if washout or growth:
                    return "LR-5"
                if capsule:
                    return "LR-4"
                return "LR-4"  # APHE only
            else:
                # No APHE: less concerning
                return "LR-3"

        # Large size (>= 20mm)
        if size_mm >= 20:
            if aphe is None:
                return "INSUFFICIENT_DATA: APHE_status_unknown_for_large_lesion"
            
            if aphe:
                if washout or capsule or growth:
                    return "LR-5"
                return "LR-4"  # APHE only
            else:
                # No APHE
                if washout or capsule or growth:
                    return "LR-4"
                return "LR-3"

        return "LR-NC"

    def _compute_overall_li_rads(self, lesions):
        """
        Determine the highest (worst) LI-RADS in the study.
        Handles INSUFFICIENT_DATA cases gracefully.
        """
        priority = {
            "LR-TR-Viable": 50,
            "LR-5": 40,
            "LR-4": 30,
            "LR-3": 20,
            "LR-TR-Nonviable": 10,
            "LR-NC": 5,
        }
        
        best = None
        best_score = -1
        has_insufficient_data = False
        
        for l in lesions:
            cat = l["derived_li_rads"]
            
            # Track insufficient data cases
            if cat and cat.startswith("INSUFFICIENT_DATA"):
                has_insufficient_data = True
                continue
            
            score = priority.get(cat, 0)
            if score > best_score:
                best = cat
                best_score = score
        
        # If all lesions have insufficient data, return that
        if best is None and has_insufficient_data:
            return "INSUFFICIENT_DATA: cannot_determine_overall_category"
        
        return best

    def _compute_temporal_response(self, studies):
        """
        Compute temporal response with explicit insufficient data handling.
        """
        if len(studies) < 2:
            last = studies[-1]["overall_derived_li_rads"] if studies else None
            return {"mRECIST": None, "LI_RADS_TR": last}

        baseline, current = studies[0], studies[-1]
        
        # Calculate viable diameters
        baseline_viable = self._sum_viable(baseline)
        current_viable = self._sum_viable(current)
        
        # Check if we have sufficient data for mRECIST
        has_baseline_size = baseline_viable > 0
        has_current_size = any(
            l["size_cm"]["longest_diameter_cm"] is not None 
            for l in current["lesions"]
        )
        
        # Check if baseline has insufficient data
        baseline_has_insufficient = any(
            l["derived_li_rads"] and l["derived_li_rads"].startswith("INSUFFICIENT_DATA")
            for l in baseline["lesions"]
        )
        
        if baseline_has_insufficient and baseline_viable == 0:
            # Baseline couldn't be properly assessed
            return {
                "mRECIST": {
                    "category": "INSUFFICIENT_DATA: baseline_study_incomplete",
                    "baseline_viable_diameter_cm": None,
                    "current_viable_diameter_cm": round(current_viable, 2) if current_viable > 0 else None,
                    "percent_change": None,
                },
                "LI_RADS_TR": self._determine_li_rads_tr(current),
            }
        
        if not has_current_size:
            return {
                "mRECIST": {
                    "category": "INSUFFICIENT_DATA: current_study_size_missing",
                    "baseline_viable_diameter_cm": round(baseline_viable, 2) if baseline_viable > 0 else None,
                    "current_viable_diameter_cm": None,
                    "percent_change": None,
                },
                "LI_RADS_TR": self._determine_li_rads_tr(current),
            }

        # Standard mRECIST calculation
        if baseline_viable == 0:
            percent_change = None
            category = "CR" if current_viable == 0 else "SD"
        else:
            percent_change = ((current_viable - baseline_viable) / baseline_viable) * 100
            if current_viable == 0:
                category = "CR"
            elif percent_change <= -30:
                category = "PR"
            elif percent_change >= 20:
                category = "PD"
            else:
                category = "SD"

        tr = self._determine_li_rads_tr(current)

        return {
            "mRECIST": {
                "category": category,
                "baseline_viable_diameter_cm": round(baseline_viable, 2),
                "current_viable_diameter_cm": round(current_viable, 2),
                "percent_change": round(percent_change, 2) if percent_change is not None else None,
            },
            "LI_RADS_TR": tr,
        }

    def _sum_viable(self, study):
        """Sum viable tumor diameter, considering derived LI-RADS"""
        total = 0
        for l in study["lesions"]:
            lr = l["derived_li_rads"]
            
            # Skip insufficient data cases
            if lr and lr.startswith("INSUFFICIENT_DATA"):
                continue
            
            aphe = l["enhancement_features"]["arterial_phase_hyperenhancement"]
            size = l["size_cm"]["longest_diameter_cm"]
            
            # If Viable TR or Active HCC (LR-4/5) or has APHE
            if lr in ["LR-TR-Viable", "LR-5", "LR-4"] or aphe:
                if size:
                    total += size
        return total

    def _validate_extraction(self, llm_out: Dict[str, Any], report_text: str) -> Dict[str, Any]:
        """
        Validate LLM extraction by checking for obvious mismatches.
        This is a safety net to catch LLM failures.
        """
        report_lower = report_text.lower()
        
        # Check for obvious APHE mentions that LLM missed
        aphe_keywords = ["arterial phase hyperenhancement", "arterial phase enhancement", 
                        "arterial hyperenhancement", "aphe", "hypervascular"]
        has_aphe_in_text = any(kw in report_lower for kw in aphe_keywords)
        
        if has_aphe_in_text and llm_out.get("arterial_phase_hyperenhancement") is None:
            print(f"WARNING: LLM missed APHE in report: {report_text[:100]}...")
            llm_out["arterial_phase_hyperenhancement"] = True
        
        # Check for washout
        washout_keywords = ["washout", "delayed phase hypoenhancement", "venous washout"]
        has_washout_in_text = any(kw in report_lower for kw in washout_keywords)
        
        if has_washout_in_text and llm_out.get("washout") is None:
            print(f"WARNING: LLM missed washout in report: {report_text[:100]}...")
            llm_out["washout"] = True
        
        # Check for LI-RADS category
        lirads_pattern = r"(LR-?\d|LR-?TR-?(Viable|Nonviable|Equivocal))"
        import re
        match = re.search(lirads_pattern, report_text, re.IGNORECASE)
        if match and not llm_out.get("li_rads_category"):
            print(f"WARNING: LLM missed LI-RADS category: {match.group()}")
            llm_out["li_rads_category"] = match.group()
        
        return llm_out

    def _determine_li_rads_tr(self, study):
        """Determine LI-RADS treatment response category"""
        viable_count = sum(1 for l in study["lesions"] if l["derived_li_rads"] == "LR-TR-Viable")
        nonviable_count = sum(1 for l in study["lesions"] if l["derived_li_rads"] == "LR-TR-Nonviable")
        insufficient_count = sum(1 for l in study["lesions"] if l["derived_li_rads"] and l["derived_li_rads"].startswith("INSUFFICIENT_DATA"))
        
        total_lesions = len(study["lesions"])
        
        # If all insufficient data
        if insufficient_count == total_lesions:
            return "INSUFFICIENT_DATA: cannot_assess_treatment_response"
        
        if viable_count > 0:
            return "LR-TR-Viable"
        if nonviable_count == total_lesions:
            return "LR-TR-Nonviable"
        
        # If untreated lesions exist, return the worst untreated score
        overall = study["overall_derived_li_rads"]
        if overall and overall in ["LR-5", "LR-4"]:
            return overall
            
        return "LR-TR-Equivocal"

    def _compute_tumor_burden(self, baseline):
        """Compute tumor burden score with insufficient data handling"""
        if not baseline or not baseline["lesions"]:
            return {"metric": "TBS", "value": "INSUFFICIENT_DATA: no_lesions"}
        
        valid_sizes = [
            l["size_cm"]["longest_diameter_cm"]
            for l in baseline["lesions"]
            if l["size_cm"]["longest_diameter_cm"] is not None
        ]
        
        if not valid_sizes:
            return {"metric": "TBS", "value": "INSUFFICIENT_DATA: no_size_measurements"}

        max_size = max(valid_sizes)
        n = len(baseline["lesions"])
        tbs = math.sqrt(max_size**2 + n**2)
        return {"metric": "TBS", "value": round(tbs, 2)}

    def _build_interpretation(self, studies, temporal):
        """Build clinical interpretation with insufficient data awareness"""
        if not studies:
            return "No imaging studies available for interpretation."
        
        baseline = studies[0]
        if not baseline["lesions"]:
            return "No lesions identified in baseline study."
        
        high = baseline["lesions"][0]
        
        # Check for insufficient data in baseline
        derived = high['derived_li_rads']
        if derived and derived.startswith("INSUFFICIENT_DATA"):
            return f"Baseline imaging incomplete: {derived.replace('INSUFFICIENT_DATA: ', '')}. Complete imaging data required for comprehensive assessment."
        
        parts = []
        
        # Baseline description
        desc = f"Baseline {derived} lesion"
        if high['segment']:
            desc += f" in segment {high['segment']}"
        
        if high['size_cm']['longest_diameter_cm']:
            desc += f" measuring {high['size_cm']['longest_diameter_cm']} cm"
        
        parts.append(desc)
        
        # Temporal response
        mrec = temporal.get("mRECIST")
        if mrec:
            category = mrec["category"]
            if category and not category.startswith("INSUFFICIENT_DATA"):
                change = mrec.get("percent_change")
                if change is not None:
                    parts.append(f"Treatment response: {category} with {change:+.1f}% change in viable tumor")
                else:
                    parts.append(f"Treatment response: {category}")
            elif category and category.startswith("INSUFFICIENT_DATA"):
                parts.append("Treatment response assessment limited by incomplete follow-up imaging data")
        
        return ". ".join(parts) + "."


# ============================================================
#    USAGE EXAMPLE
# ============================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os

    load_dotenv()
    API_KEY = os.getenv("OPENAI_API_KEY")

    sample_input = {
                # "radiology": {
        #     "studies": [
        #         {
        #             "date": "2025-01-15",
        #             "modality": "CT Triphasic",
        #             "imaging_center": "Apollo Radiology",
        #             "radiology_report_text":
        #                 "Cirrhotic liver with arterially enhancing lesion in segment 5. Washout noted in delayed phase. No PVTT. Consistent with LR-5.",
        #             "lesions": [
        #                 {
        #                     "lesion_id": "L1",
        #                     "segment": 5,
        #                     "size_cm": {
        #                         "longest_diameter_cm": 4.2,
        #                         "transverse_cm": 3.1
        #                     },
        #                     "pvtt": False,
        #                     "extrahepatic_metastasis": False
        #                 }
        #             ],
        #             "files": {"radiology_pdf": None, "dicom_zip": None},
        #         },

        #         {
        #             "date": "2025-03-20",
        #             "modality": "MRI Liver",
        #             "imaging_center": "Medanta Hospital",
        #             "radiology_report_text":
        #                 "Previously treated lesion in segment 5 shows reduced enhancement. Partial necrosis. No residual APHE or washout.",
        #             "lesions": [
        #                 {
        #                     "lesion_id": "L1",
        #                     "segment": 5,
        #                     "size_cm": {
        #                         "longest_diameter_cm": 2.2,
        #                         "transverse_cm": 1.4
        #                     },
        #                     "pvtt": False,
        #                     "extrahepatic_metastasis": False,
        #                     "treated": True # Explicitly marked treated
        #                 }
        #             ],
        #             "files": {"radiology_pdf": None, "dicom_zip": None},
        #         }
        #     ]
        # }
        
        
        "radiology": {
            "studies": [
                {
                    "date": None,
                    "modality": "CT / MRI Multiphasic (LI-RADS Assessment)",
                    "imaging_center": "",
                    "radiology_report_text": "Single hepatic lesion measuring 4.5 cm demonstrating arterial phase hyperenhancement with washout. Classified as LI-RADS LR-5. No portal vein tumor thrombus noted.",
                    "lesions": [
                        {
                            "lesion_id": "L1",
                            "segment": None,
                            "size_cm": {
                                "longest_diameter_cm": 4.5,
                                "transverse_cm": None
                            },
                            "pvtt": False,
                            "extrahepatic_metastasis": False
                        }
                    ],
                    "files": {
                        "radiology_pdf": None,
                        "dicom_zip": None
                    }
                },
                {
                    "date": None,
                    "modality": "Post-TACE follow-up imaging",
                    "imaging_center": "",
                    "radiology_report_text": "Post-treatment imaging demonstrates partial response with residual viable enhancing tumor consistent with LR-TR Viable.",
                    "lesions": [
                        {
                            "lesion_id": "L1",
                            "segment": None,
                            "size_cm": {
                                "longest_diameter_cm": None,
                                "transverse_cm": None
                            },
                            "pvtt": False,
                            "extrahepatic_metastasis": False
                        }
                    ],
                    "files": {
                        "radiology_pdf": None,
                        "dicom_zip": None
                    }
                }
            ]
        }
    }

    if API_KEY:
        llm = OpenAILLM(api_key=API_KEY)
        agent = RadiologyAgent(llm=llm)

        out = agent.process(sample_input["radiology"])
        print(json.dumps(out, indent=2))
    else:
        print("Please set OPENAI_API_KEY env variable to run the example.")