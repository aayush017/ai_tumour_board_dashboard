
import json
import re
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from openai import OpenAI



class OpenAILLM:
    """
    Production LLM client that extracts structured radiology features
    using GPT-4o. Replaces MockLLM completely.
    """

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def extract(self, prompt: str) -> Dict[str, Any]:
        """
        Calls GPT-4o and expects a JSON dictionary back.
        If the model returns malformed JSON, it attempts recovery.
        """

        system_prompt = """
You are a radiology information extraction model.
Extract ONLY the following fields from the provided report:

{
   "arterial_phase_hyperenhancement": true/false/null,
   "washout": true/false/null,
   "enhancing_capsule": true/false/null,
   "threshold_growth": true/false/null,
   "pvtt": true/false/null,
   "extrahepatic_metastasis": true/false/null,
   "treated": true/false/null,
   "size_longest_cm": number/null,
   "size_transverse_cm": number/null
}

Rules:
- If not mentioned → return null
- If explicitly negated → false
- Try extracting size from text like "4.2 cm", "4.2 × 3.1 cm"
- Output strictly valid JSON with keys exactly as above
        """

        completion = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )

        raw = completion.choices[0].message.content

        # Attempt to parse the JSON returned
        try:
            return json.loads(raw)
        except:
            # Attempt best-effort JSON recovery
            try:
                fixed = raw[raw.find("{"): raw.rfind("}") + 1]
                return json.loads(fixed)
            except:
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
                }

@dataclass
class RadiologyAgent:
    llm: Any
    assign_missing_ids: bool = True
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
            return {"score": 0.0, "extraction_quality": "unknown", "notes": "No studies processed."}

        # Initialize accumulators
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

                # LI-RADS clarity
                lr = lesion["li_rads"]
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

        # Label
        if score > 0.85:
            label = "high"
        elif score > 0.65:
            label = "medium"
        else:
            label = "low"

        return score
         


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
                    "radiology_agent_confidence" : confidence
                }
            }
        }

    def _process_study(self, study, study_index):
        date = study.get("date")
        modality = study.get("modality")
        report_text = study.get("radiology_report_text", "") or ""
        lesions_in = study.get("lesions", []) or []
        processed_lesions = []

        # If no lesions given → try extract from GPT-4o
        if not lesions_in:
            llm_out = self.llm.extract(report_text)
            if llm_out.get("size_longest_cm") is not None:
                processed_lesions.append({
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
                    "li_rads": None,
                    "pvtt": llm_out["pvtt"],
                    "extrahepatic_metastasis": llm_out["extrahepatic_metastasis"],
                    "treated": llm_out["treated"],
                })
        else:
            # Structured lesions → enrich with GPT-4o
            for lesion in lesions_in:
                lesion_id = lesion.get("lesion_id") or f"L{len(processed_lesions)+1}"
                segment = lesion.get("segment")
                size = lesion.get("size_cm", {})
                longest, transverse = size.get("longest_diameter_cm"), size.get("transverse_cm")

                # Build prompt for GPT-4o
                prompt = f"""
Extract lesion features from this radiology report:

REPORT:
{report_text}

LESION:
ID: {lesion_id}
Segment: {segment}
Size: {longest} x {transverse} cm

Return JSON only.
                """

                llm_out = self.llm.extract(prompt)

                if longest is None and llm_out["size_longest_cm"] is not None:
                    longest = llm_out["size_longest_cm"]
                if transverse is None and llm_out["size_transverse_cm"] is not None:
                    transverse = llm_out["size_transverse_cm"]

                processed_lesions.append({
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
                    "li_rads": None,
                    "pvtt": lesion.get("pvtt") or llm_out["pvtt"],
                    "extrahepatic_metastasis": lesion.get("extrahepatic_metastasis") or llm_out["extrahepatic_metastasis"],
                    "treated": llm_out["treated"],
                })

        # Assign LI-RADS
        for lesion in processed_lesions:
            lesion["li_rads"] = self._assign_li_rads(lesion)

        overall_li = self._compute_overall_li_rads(processed_lesions)
        cleaned_report = report_text.strip()

        return {
            "date": date,
            "modality": modality,
            "lesions": processed_lesions,
            "radiology_report_text": cleaned_report,
            "overall_li_rads": overall_li,
        }

    # ------- LI-RADS, TR, mRECIST, TBS, interpretation methods  --------
    # ------------------------------------------------------------------------------

    def _assign_li_rads(self, lesion):
        ef = lesion["enhancement_features"]
        aphe, wash = ef["arterial_phase_hyperenhancement"], ef["washout"]
        capsule = ef["enhancing_capsule"]
        treated = lesion["treated"]

        size = lesion["size_cm"]["longest_diameter_cm"]
        size_ok = size is not None and size >= 1.0

        if treated:
            if aphe or wash:
                return "LR-TR-Viable"
            return "LR-TR-Nonviable"

        if aphe and (wash or capsule) and size_ok:
            return "LR-5"
        if aphe and size_ok:
            return "LR-4"
        if not aphe and (wash or capsule):
            return "LR-3"
        return "LR-3"

    def _compute_overall_li_rads(self, lesions):
        priority = {
            "LR-TR-Viable": 50, "LR-5": 40, "LR-4": 30,
            "LR-3": 20, "LR-TR-Nonviable": 10, None: 0,
        }
        best = None
        best_score = -1
        for l in lesions:
            cat = l["li_rads"]
            score = priority.get(cat, 0)
            if score > best_score:
                best = cat
                best_score = score
        return best

    def _compute_temporal_response(self, studies):
        if len(studies) < 2:
            last = studies[-1]["overall_li_rads"] if studies else None
            return {"mRECIST": None, "LI_RADS_TR": last}

        baseline, current = studies[0], studies[-1]
        baseline_viable = self._sum_viable(baseline)
        current_viable = self._sum_viable(current)

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
                "percent_change": round(percent_change, 2) if percent_change else None,
            },
            "LI_RADS_TR": tr,
        }


    def _sum_viable(self, study):
        total = 0
        for l in study["lesions"]:
            aphe = l["enhancement_features"]["arterial_phase_hyperenhancement"]
            size = l["size_cm"]["longest_diameter_cm"]
            if l["li_rads"] == "LR-TR-Viable" or aphe:
                if size:
                    total += size
        return total

    def _determine_li_rads_tr(self, study):
        viable = any(l["li_rads"] == "LR-TR-Viable" for l in study["lesions"])
        nonviable = all(l["li_rads"] == "LR-TR-Nonviable" for l in study["lesions"])
        if viable:
            return "LR-TR-Viable"
        if nonviable:
            return "LR-TR-Nonviable"
        return "LR-TR-Equivocal"

    def _compute_tumor_burden(self, baseline):
        if not baseline or not baseline["lesions"]:
            return {"metric": "TBS", "value": None}
        max_size = max(
            l["size_cm"]["longest_diameter_cm"]
            for l in baseline["lesions"]
            if l["size_cm"]["longest_diameter_cm"]
        )
        n = len(baseline["lesions"])
        tbs = math.sqrt(max_size**2 + n**2)
        return {"metric": "TBS", "value": round(tbs, 2)}

    def _build_interpretation(self, studies, temporal):
        if not studies:
            return ""
        baseline = studies[0]
        high = baseline["lesions"][0]
        mrec = temporal["mRECIST"]

        parts = [
            f"Baseline {high['li_rads']} lesion in segment {high['segment']} with longest diameter {high['size_cm']['longest_diameter_cm']} cm"
        ]

        if mrec:
            parts.append(
                f"{mrec['category']} with {mrec['percent_change']}% change in viable tumor"
            )

        return ". ".join(parts) + "."


# ============================================================
#    USAGE EXAMPLE (PUT YOUR GPT-4o KEY BELOW)
# ============================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os

    load_dotenv()  # load .env file if present
    API_KEY= os.getenv("OPENAI_API_KEY")

    sample_input = {
        "radiology": {
            "studies": [
                {
                    "date": "2025-01-15",
                    "modality": "CT Triphasic",
                    "imaging_center": "Apollo Radiology",
                    "radiology_report_text":
                        "Cirrhotic liver with arterially enhancing lesion in segment 5. Washout noted in delayed phase. No PVTT.",
                    "lesions": [
                        {
                            "lesion_id": "L1",
                            "segment": 5,
                            "size_cm": {
                                "longest_diameter_cm": 4.2,
                                "transverse_cm": 3.1
                            },
                            "pvtt": False,
                            "extrahepatic_metastasis": False
                        }
                    ],
                    "files": {"radiology_pdf": None, "dicom_zip": None},
                },

                {
                    "date": "2025-03-20",
                    "modality": "MRI Liver",
                    "imaging_center": "Medanta Hospital",
                    "radiology_report_text":
                        "Previously treated lesion in segment 5 shows reduced enhancement. Partial necrosis.",
                    "lesions": [
                        {
                            "lesion_id": "L1",
                            "segment": 5,
                            "size_cm": {
                                "longest_diameter_cm": 2.2,
                                "transverse_cm": 1.4
                            },
                            "pvtt": False,
                            "extrahepatic_metastasis": False
                        }
                    ],
                    "files": {"radiology_pdf": None, "dicom_zip": None},
                }
            ]
        }
    }

    llm = OpenAILLM(api_key=API_KEY)
    agent = RadiologyAgent(llm=llm)

    out = agent.process(sample_input["radiology"])
    print(json.dumps(out, indent=2))
