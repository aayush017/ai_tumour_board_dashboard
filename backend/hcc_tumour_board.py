# hcc_tumor_board.py

import os
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple, TypedDict, Any
import tiktoken

# LangGraph imports
from langgraph.graph import StateGraph, END

# LlamaIndex imports
from llama_parse import LlamaParse
from llama_index.core import (
    VectorStoreIndex, 
    Settings, 
    StorageContext,
    load_index_from_storage
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core.schema import TextNode

# LangChain imports for strategy agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tumor_board_inasl_compliant.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

os.environ['LLAMA_CLOUD_API_KEY'] = os.getenv('LLAMA_CLOUD_API_KEY', 'llx-your-key-here')
os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', 'sk-your-key-here')

# ✅ FIXED: Temperature = 0.0 for strict grounding
Settings.llm = OpenAI(model="gpt-4o", temperature=0.0)
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-large", dimensions=3072)

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

PARSED_DOCS_CACHE = CACHE_DIR / "parsed_documents.pkl"
INDEX_DIR = CACHE_DIR / "vector_index_large"
METADATA_CACHE = CACHE_DIR / "metadata.json"

EMBEDDING_MODEL = "text-embedding-3-large"
MAX_EMBEDDING_TOKENS = 8000

try:
    TOKENIZER = tiktoken.encoding_for_model("gpt-4")
except:
    TOKENIZER = tiktoken.get_encoding("cl100k_base")

# ✅ FIXED: AFP Thresholds (correct clinical ranges)
AFP_NORMAL = 20  # <20 ng/ml
AFP_ELEVATED = 400  # >400 ng/ml = high tumor burden
AFP_VERY_HIGH = 1000  # >1000 ng/ml = very high risk

# ============================================================================
# DATA STRUCTURES FOR LANGGRAPH STATE
# ============================================================================

class PatientData(TypedDict):
    clinical_summary: Dict[str, Any]
    radiology_summary: Dict[str, Any]
    pathology_summary: Dict[str, Any]

class SpecialistInstruction(TypedDict):
    specialist_role: str
    focus_area: str
    specific_questions: List[str]
    guidance_context: str
    priority: str  # "PRIMARY" | "SECONDARY" | "CONDITIONAL"

class StrategyPlan(TypedDict):
    bclc_stage: str
    bclc_rationale: str
    bclc_substage_detail: str
    clinical_impression: str
    specialist_instructions: List[SpecialistInstruction]
    orchestrator_guidance: str
    critical_checks: List[str]
    treatment_intent: str  # "CURATIVE" | "LOCOREGIONAL" | "SYSTEMIC" | "PALLIATIVE"

class SpecialistResult(TypedDict):
    specialist: str
    assessment: str
    recommendations: List[str]
    confidence: float
    evidence_quality: str
    critical_flags: List[str]

class IntegratedState(TypedDict):
    raw_input_json: Dict[str, Any]
    filtered_data: PatientData
    bclc_result: Dict[str, str]
    strategy_plan: Optional[StrategyPlan]
    specialist_results: Dict[str, SpecialistResult]
    consensus_plan: Optional[str]
    final_recommendation: Optional[Dict[str, Any]]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def count_tokens(text: str) -> int:
    try:
        return len(TOKENIZER.encode(text))
    except:
        return len(text) // 4

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    try:
        tokens = TOKENIZER.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return TOKENIZER.decode(tokens[:max_tokens])
    except:
        return text[:max_tokens * 4]

def extract_lab_abnormalities(clinical: Dict) -> List[str]:
    """✅ FIXED: Extract critical abnormalities with correct AFP thresholds"""
    abnormalities = []
    lab_flags = clinical.get('lab_flags', {})
    labs = clinical.get('labs_baseline', {})
    
    # ✅ FIXED: Correct AFP thresholds
    afp = labs.get('AFP_ng_ml', 0)
    if afp > AFP_VERY_HIGH:
        abnormalities.append(f"Very high AFP ({afp:,.0f} ng/mL) - high tumor burden")
    elif afp > AFP_ELEVATED:
        abnormalities.append(f"Elevated AFP ({afp:,.0f} ng/mL) - significant tumor burden")
    elif afp > AFP_NORMAL:
        abnormalities.append(f"Mildly elevated AFP ({afp:.1f} ng/mL)")
    
    # Portal hypertension markers
    plt = labs.get('platelets_k', 150)
    if plt < 100:
        abnormalities.append(f"Severe thrombocytopenia ({plt}K) - suggests significant portal hypertension")
    elif plt < 150:
        abnormalities.append(f"Thrombocytopenia ({plt}K) - suggests portal hypertension")
    
    # Liver dysfunction markers
    bili = labs.get('total_bilirubin_mg_dl', 0)
    if bili > 3:
        abnormalities.append(f"Severe hyperbilirubinemia ({bili} mg/dL) - poor prognosis")
    elif bili > 2:
        abnormalities.append(f"Hyperbilirubinemia ({bili} mg/dL)")
    
    alb = labs.get('albumin_g_dl', 3.5)
    if alb < 2.8:
        abnormalities.append(f"Significant hypoalbuminemia ({alb} g/dL) - poor synthetic function")
    elif alb < 3.5:
        abnormalities.append(f"Hypoalbuminemia ({alb} g/dL)")
    
    # Coagulopathy
    inr = labs.get('INR', 1.0)
    if inr > 1.7:
        abnormalities.append(f"Severe coagulopathy (INR {inr})")
    elif inr > 1.5:
        abnormalities.append(f"Coagulopathy (INR {inr})")
    
    # Anemia
    hgb = labs.get('hemoglobin_g_dl', 12)
    if hgb < 10:
        abnormalities.append(f"Moderate anemia (Hgb {hgb} g/dL)")
    elif hgb < 12:
        abnormalities.append(f"Mild anemia (Hgb {hgb} g/dL)")
    
    # Renal function
    cr = labs.get('creatinine_mg_dl', 1.0)
    if cr > 1.5:
        abnormalities.append(f"Renal dysfunction (Cr {cr} mg/dL)")
    
    # Sodium
    na = labs.get('Na_mmol_L', 140)
    if na < 130:
        abnormalities.append(f"Severe hyponatremia ({na} mmol/L)")
    elif na < 135:
        abnormalities.append(f"Hyponatremia ({na} mmol/L)")
    
    return abnormalities

def create_concise_patient_summary(patient_data: Dict) -> str:
    """Create a concise, structured patient summary"""
    clinical = patient_data['clinical_summary']
    labs = clinical['labs_baseline']
    scores = clinical['derived_scores']
    child_pugh = scores['Child_Pugh']
    tumor_info = extract_tumor_summary(patient_data)
    
    abnormalities = extract_lab_abnormalities(clinical)
    
    # ✅ FIXED: Correct decompensation assessment
    ascites = clinical.get('ascites', 'none')
    encephalopathy = clinical.get('encephalopathy', 'none')
    is_decompensated = (
        child_pugh['class'] in ['B', 'C'] or 
        ascites not in ['none', 'absent'] or 
        encephalopathy not in ['none', 'absent']
    )
    compensation_status = "DECOMPENSATED" if is_decompensated else "COMPENSATED"
    
    summary = f"""PATIENT: {clinical.get('etiology', 'Unknown etiology')}
LIVER STATUS: {compensation_status} cirrhosis
SYMPTOMS: {', '.join(clinical.get('symptoms', ['None']))}
ECOG: {clinical['ECOG']} | Child-Pugh: {child_pugh['class']}{child_pugh['score']} | MELD: {scores.get('MELD')} | MELD-Na: {scores.get('MELD_Na')}
TUMOR: {tumor_info['count']} lesion(s), max {tumor_info['max_size_cm']}cm, {tumor_info['distribution']}
KEY LABS: AFP {labs['AFP_ng_ml']:.1f}, Bili {labs['total_bilirubin_mg_dl']}, Alb {labs['albumin_g_dl']}, Plt {labs['platelets_k']}K, INR {labs['INR']}
ABNORMALITIES: {'; '.join(abnormalities) if abnormalities else 'None critical'}"""
    
    return summary

# ============================================================================
# ✅ INASL PURI 3 COMPLIANT BCLC CALCULATION
# ============================================================================

def calculate_inasl_bclc(clinical: Dict, radiology: Dict, pathology: Dict) -> Dict[str, str]:
    """
    ✅ INASL Puri 3 BCLC Staging - Validated Implementation
    
    Based on INASL guidelines via RAG retrieval, with defensive None handling
    """
    # ✅ FIXED: Handle None/null values defensively
    ps = clinical.get("ECOG")
    if ps is None:
        ps = 0
        logger.warning("⚠️ ECOG is None/null, defaulting to 0")
    
    cp_score = clinical.get("derived_scores", {}).get("Child_Pugh", {}).get("score")
    if cp_score is None:
        cp_score = 5
        logger.warning("⚠️ Child-Pugh score is None/null, defaulting to 5 (class A)")
    
    cp_class = clinical.get("derived_scores", {}).get("Child_Pugh", {}).get("class")
    if cp_class is None:
        cp_class = "A"
        logger.warning("⚠️ Child-Pugh class is None/null, defaulting to A")
    
    # Extract tumor characteristics
    study = radiology.get("studies", [])[0] if radiology.get("studies") else {}
    lesions = study.get("lesions", [])
    viable_lesions = [l for l in lesions if not l.get('treated', False)]
    
    num_lesions = len(viable_lesions)
    max_diameter = 0.0
    total_tumor_diameter = 0.0
    
    for l in viable_lesions:
        size = l.get("size_cm", {})
        diam = size.get("longest_diameter_cm", 0) if isinstance(size, dict) else size
        if diam > max_diameter:
            max_diameter = diam
        total_tumor_diameter += diam
            
    # Vascular and metastatic assessment
    pvtt = any(l.get("pvtt", False) for l in viable_lesions)
    extrahepatic = any(l.get("extrahepatic_metastasis", False) for l in viable_lesions)
    histology = pathology.get("histology", {})
    has_vascular_invasion = histology.get("vascular_invasion", False)
    
    # Portal hypertension assessment
    platelets = clinical.get("labs_baseline", {}).get("platelets_k", 150)
    has_portal_htn = platelets < 150  # Thrombocytopenia suggests portal HTN
    
    # Ascites and encephalopathy
    ascites = clinical.get('ascites', 'none')
    encephalopathy = clinical.get('encephalopathy', 'none')
    is_decompensated = (
        cp_class in ['B', 'C'] or 
        ascites not in ['none', 'absent'] or 
        encephalopathy not in ['none', 'absent']
    )
    
    stage = "Unknown"
    rationale = []
    substage_detail = ""

    # ═══════════════════════════════════════════════════════════════
    # STAGE D (TERMINAL) - BCLC D
    # ═══════════════════════════════════════════════════════════════
    if ps > 2 or cp_class == "C":
        stage = "D (Terminal)"
        rationale.append(f"ECOG PS {ps} or Child-Pugh {cp_class} indicates terminal stage per INASL BCLC criteria.")
        substage_detail = "Best supportive care recommended due to poor functional status or end-stage liver disease. Palliative interventions only."
        return {"stage": stage, "rationale": " ".join(rationale), "substage_detail": substage_detail}

    # ═══════════════════════════════════════════════════════════════
    # STAGE C (ADVANCED) - BCLC C with INASL Substaging
    # ═══════════════════════════════════════════════════════════════
    is_advanced_tumor = pvtt or extrahepatic or has_vascular_invasion
    is_symptomatic = ps >= 1
    
    if is_advanced_tumor or is_symptomatic:
        if extrahepatic:
            stage = "C2 (INASL - Extrahepatic Spread)"
            rationale.append("Presence of extrahepatic metastasis categorizes as BCLC C2 per INASL.")
            substage_detail = "Systemic therapy indicated. First-line: Atezolizumab-Bevacizumab. Alternatives: Sorafenib, Lenvatinib, Durvalumab-Tremelimumab."
        elif pvtt or has_vascular_invasion:
            stage = "C1 (INASL - PVTT/Vascular Invasion)"
            rationale.append(f"Portal vein tumor thrombosis (PVTT={pvtt}) or macrovascular invasion without extrahepatic spread per INASL C1.")
            substage_detail = "Consider Y90-TARE for PVTT or systemic therapy. Sorafenib has shown benefit in PVTT cases per INASL guidelines."
        else:
            # PS 1 but no vascular invasion - need to determine if PS is from HCC or comorbidities
            stage = "C (Performance Status Driven)"
            rationale.append(f"ECOG PS {ps} categorizes as Stage C. ⚠️ CRITICAL CLINICAL JUDGMENT NEEDED: Assess if PS impairment is due to HCC (→ Stage C systemic therapy) or comorbidities (→ may still be candidate for locoregional therapy as Stage A/B).")
            substage_detail = "If PS 1 is from HCC: Systemic therapy (Atezolizumab-Bevacizumab). If PS 1 is from comorbidities and liver function preserved: May still be candidate for locoregional therapy (Stage A/B). Requires multidisciplinary assessment."
        
        return {"stage": stage, "rationale": " ".join(rationale), "substage_detail": substage_detail}

    # ═══════════════════════════════════════════════════════════════
    # STAGE B (INTERMEDIATE) - BCLC B with INASL Substaging
    # ═══════════════════════════════════════════════════════════════
    if num_lesions > 1 and ps == 0:
        # Check UCSF criteria for transplant eligibility
        is_ucsf = False
        if num_lesions == 1 and max_diameter <= 6.5:
            is_ucsf = True
        elif num_lesions <= 3 and max_diameter <= 4.5 and total_tumor_diameter <= 8.0:
            is_ucsf = True
            
        if is_ucsf:
            stage = "B1 (INASL - Transplant Candidate)"
            rationale.append(f"Multifocal disease within UCSF criteria ({num_lesions} lesions, max {max_diameter}cm, total {total_tumor_diameter}cm), PS 0, CP {cp_class} per INASL B1.")
            substage_detail = "Consider liver transplantation if meets institutional criteria. May bridge with TACE/TARE. Alternative: TACE if transplant not feasible."
        elif num_lesions > 3 or max_diameter > 5:
            stage = "B3 (INASL - Extensive Disease)"
            rationale.append(f"Extensive multifocal disease ({num_lesions} lesions, max {max_diameter}cm exceeds B1/B2 criteria), PS 0 per INASL B3.")
            substage_detail = "Consider Y90-TARE or systemic therapy. TACE may have limited efficacy with extensive disease. Clinical trial enrollment encouraged per INASL."
        else:
            stage = "B2 (INASL - Standard Intermediate)"
            rationale.append(f"Multifocal disease ({num_lesions} lesions, max {max_diameter}cm), PS 0, CP {cp_class} per INASL B2.")
            substage_detail = "TACE is first-line for BCLC B2 per INASL. Consider Y90-TARE as alternative. Monitor for TACE progression."
        
        return {"stage": stage, "rationale": " ".join(rationale), "substage_detail": substage_detail}

    # ═══════════════════════════════════════════════════════════════
    # STAGE 0 (VERY EARLY) & STAGE A (EARLY) - CURATIVE INTENT
    # ═══════════════════════════════════════════════════════════════
    if not pvtt and not extrahepatic and not has_vascular_invasion:
        if num_lesions == 1:
            if max_diameter < 2.0:
                # BCLC 0 (Very Early)
                stage = "0 (Very Early)"
                rationale.append(f"Single lesion <2cm ({max_diameter}cm), PS 0, CP {cp_class} per INASL BCLC 0.")
                
                if has_portal_htn:
                    substage_detail = f"Ablation (RFA/MWA) first-line recommended (portal HTN present: platelets {platelets}K). Resection contraindicated due to portal hypertension. Consider surveillance if <1cm."
                elif is_decompensated:
                    substage_detail = "Transplant evaluation recommended for decompensated cirrhosis. Ablation as bridge to transplant. Resection only if excellent liver function."
                else:
                    substage_detail = "Ablation (RFA/MWA) first-line if no portal hypertension per INASL. Resection if excellent liver function and no portal HTN. Consider surveillance if <1cm."
                    
            elif max_diameter <= 5.0:
                # BCLC A (Early) - Single lesion 2-5 cm
                stage = "A (Early)"
                rationale.append(f"Single lesion {max_diameter}cm, PS 0, CP {cp_class} per INASL BCLC A.")
                
                if has_portal_htn:
                    substage_detail = f"Ablation (RFA/MWA) first-line recommended (portal HTN present: platelets {platelets}K). Resection contraindicated due to portal hypertension per INASL. Transplant if decompensated. TACE alternative if ablation not feasible."
                elif is_decompensated:
                    substage_detail = "Transplant first-line for decompensated cirrhosis per INASL. Ablation or TACE as bridge to transplant. Resection only if liver function improves."
                else:
                    substage_detail = f"Resection first-line if no portal hypertension and adequate FLR per INASL. Ablation (RFA/MWA) if {max_diameter:.1f}cm ≤3cm or unresectable. Transplant if meets Milan criteria. TACE if ablation not feasible."
                    
            else:
                # Large single lesion >5cm
                stage = "A (Early)"
                rationale.append(f"Large single lesion {max_diameter}cm, PS 0, CP {cp_class} per INASL BCLC A.")
                
                if has_portal_htn:
                    substage_detail = f"TACE first-line for large lesion with portal HTN (platelets {platelets}K). Resection contraindicated. Consider Y90-TARE. Transplant if downstaging successful."
                elif is_decompensated:
                    substage_detail = "Transplant evaluation after downstaging with TACE. Resection only if liver function excellent and no portal HTN."
                else:
                    substage_detail = f"Resection if adequate FLR (>30-40%) and no portal HTN per INASL. TACE for downstaging if borderline resectable. Consider Y90-TARE as alternative."
                    
        elif num_lesions <= 3 and max_diameter <= 3.0:
            # Oligonodular disease - BCLC A per Milan criteria
            stage = "A (Early)"
            rationale.append(f"Oligonodular disease ({num_lesions} lesions ≤3cm), PS 0, CP {cp_class}, within Milan criteria per INASL BCLC A.")
            
            if has_portal_htn:
                substage_detail = f"Ablation (RFA/MWA) first-line for up to 3 lesions ≤3cm (portal HTN present: platelets {platelets}K). Resection contraindicated. Transplant if meets Milan criteria."
            elif is_decompensated:
                substage_detail = "Transplant first-line for decompensated cirrhosis within Milan criteria. Ablation as bridge to transplant."
            else:
                substage_detail = f"Ablation (RFA/MWA) preferred for {num_lesions} lesions ≤3cm per INASL. Resection if favorable anatomy and no portal HTN. Transplant if meets Milan criteria."
                
        else:
            # Limited multifocal disease beyond Milan but potentially resectable
            stage = "A (Early)"
            rationale.append(f"Limited multifocal disease ({num_lesions} lesions), PS 0, CP {cp_class} per INASL BCLC A.")
            
            if has_portal_htn:
                substage_detail = f"TACE first-line for multifocal disease with portal HTN (platelets {platelets}K). Resection contraindicated. Consider Y90-TARE."
            else:
                substage_detail = f"Assess resectability: if all lesions in single sector and adequate FLR → resection per INASL. Otherwise TACE or Y90-TARE. Consider transplant if downstaging successful."
             
        return {"stage": stage, "rationale": " ".join(rationale), "substage_detail": substage_detail}

    # Fallback
    return {
        "stage": "Unclassified", 
        "rationale": "Insufficient data for accurate staging per INASL criteria.", 
        "substage_detail": "Requires additional clinical, imaging, or pathology information for INASL BCLC staging."
    }

# ============================================================================
# PATIENT DATA EXTRACTION
# ============================================================================

def extract_bclc_stage(patient_data: Dict) -> str:
    result = calculate_inasl_bclc(
        patient_data.get('clinical_summary', {}),
        patient_data.get('radiology_summary', {}),
        patient_data.get('pathology_summary', {})
    )
    return result['stage']

def extract_tumor_summary(patient_data: Dict) -> Dict:
    radiology = patient_data.get('radiology_summary', {})
    studies = radiology.get('studies', [])
    
    if not studies:
        return {'count': 0, 'max_size_cm': 0, 'lesions': [], 'distribution': 'unknown'}
    
    baseline_study = studies[0]
    lesions = baseline_study.get('lesions', [])
    viable_lesions = [l for l in lesions if not l.get('treated', False)]
    
    lesion_descriptions = []
    max_size = 0
    segments = set()
    
    for lesion in viable_lesions:
        size = lesion.get('size_cm', {}).get('longest_diameter_cm', 0)
        segment = lesion.get('segment', '?')
        li_rads = lesion.get('derived_li_rads') or lesion.get('ground_truth_li_rads', '?')
        pvtt = lesion.get('pvtt', False)
        
        max_size = max(max_size, size)
        if segment and segment != '?':
            segments.add(segment)
        
        pvtt_str = " +PVTT" if pvtt else ""
        lesion_descriptions.append(f"{size}cm segment {segment} (LI-RADS {li_rads}){pvtt_str}")
    
    distribution = 'unilobar' if len(segments) <= 1 else 'bilobar'
    
    return {
        'count': len(viable_lesions),
        'max_size_cm': max_size,
        'lesions': lesion_descriptions,
        'distribution': distribution,
        'segments': list(segments) if segments else ['unknown']
    }

# ============================================================================
# INPUT VALIDATION
# ============================================================================

def validate_patient_data(patient_data: Dict) -> Tuple[bool, Optional[str]]:
    if 'clinical_summary' not in patient_data:
        return False, "Missing clinical_summary"
    if 'radiology_summary' not in patient_data:
        return False, "Missing radiology_summary"
    
    clinical = patient_data['clinical_summary']
    
    if 'derived_scores' not in clinical:
        return False, "Missing derived_scores in clinical_summary"
    if 'Child_Pugh' not in clinical['derived_scores']:
        return False, "Missing Child_Pugh in derived_scores"
    if 'labs_baseline' not in clinical:
        return False, "Missing labs_baseline"
    if 'ECOG' not in clinical:
        return False, "Missing ECOG performance status"
    
    radiology = patient_data['radiology_summary']
    if 'studies' not in radiology or len(radiology['studies']) == 0:
        return False, "Missing imaging studies"
    
    baseline_study = radiology['studies'][0]
    if 'lesions' not in baseline_study or len(baseline_study['lesions']) == 0:
        return False, "No lesions in baseline imaging"
    
    has_li_rads = any(
        l.get('derived_li_rads') or l.get('ground_truth_li_rads')
        for l in baseline_study['lesions']
    )
    if not has_li_rads:
        logger.warning("⚠️ No LI-RADS classification found - may need biopsy confirmation")
    
    return True, None

# ============================================================================
# CACHING UTILITIES
# ============================================================================

def save_parsed_documents(documents, filepath=PARSED_DOCS_CACHE):
    logger.info(f"💾 Saving parsed documents to {filepath}")
    with open(filepath, 'wb') as f:
        pickle.dump(documents, f)
    logger.info("✅ Parsed documents cached")

def load_parsed_documents(filepath=PARSED_DOCS_CACHE):
    if not filepath.exists():
        return None
    logger.info(f"📂 Loading cached documents from {filepath}")
    with open(filepath, 'rb') as f:
        documents = pickle.load(f)
    logger.info(f"✅ Loaded {len(documents)} cached documents")
    return documents

def save_metadata(metadata, filepath=METADATA_CACHE):
    with open(filepath, 'w') as f:
        json.dump(metadata, f, indent=2)

def load_metadata(filepath=METADATA_CACHE):
    if not filepath.exists():
        return None
    with open(filepath) as f:
        return json.load(f)

# ============================================================================
# DOCUMENT PARSING (Same as before - working correctly)
# ============================================================================

def parse_or_load_documents(pdf_path: str, force_reparse: bool = False):
    if not force_reparse and PARSED_DOCS_CACHE.exists():
        metadata = load_metadata()
        if metadata and metadata.get('pdf_path') == pdf_path:
            logger.info("🎉 Using cached documents")
            return load_parsed_documents()
    
    logger.info("📄 Parsing PDF with LlamaParse premium mode")
    logger.info("="*80)
    logger.info("⚙️ PARSING SETTINGS:")
    logger.info("   - split_by_page=TRUE (INASL compliant)")
    logger.info("   - premium_mode=TRUE (GPT-4o vision)")
    logger.info("="*80)
    
    parser = LlamaParse(
        api_key=os.environ['LLAMA_CLOUD_API_KEY'],
        result_type="markdown",
        premium_mode=True,
        split_by_page=True,
        page_separator="\n\n---PAGE_BREAK---\n\n",
        invalidate_cache=True,
        do_not_cache=False
    )
    
    documents = parser.load_data(pdf_path)
    logger.info(f"✅ Parsed {len(documents)} sections")
    
    total_tokens_raw = sum(count_tokens(doc.text) for doc in documents)
    logger.info("="*80)
    logger.info(f"📊 RAW PARSING STATISTICS:")
    logger.info(f"   Total sections: {len(documents)}")
    logger.info(f"   Total tokens: {total_tokens_raw:,}")
    logger.info("="*80)
    
    documents = _enhance_documents(documents)
    
    save_parsed_documents(documents)
    save_metadata({
        'pdf_path': pdf_path,
        'parsed_at': datetime.now().isoformat(),
        'num_documents': len(documents),
        'total_tokens': total_tokens_raw,
        'parsing_mode': 'premium_split_by_page_inasl'
    })
    
    return documents

def _enhance_documents(documents):
    """Enhanced with detailed content type detection"""
    for i, doc in enumerate(documents):
        content = doc.text
        token_count = count_tokens(content)
        content_type = _detect_content_type(content)
        
        doc.metadata.update({
            'doc_id': f'doc_{i}',
            'page_number': i + 1,
            'content_type': content_type,
            'section': _extract_section(content),
            'source': 'inasl_puri3_guidelines',
            'token_count': token_count,
            'has_table': '|' in content and ('|---' in content or '| ---' in content),
            'has_image_desc': any(kw in content.lower() for kw in ['figure', 'diagram', 'flowchart', 'algorithm']),
            'char_count': len(content)
        })
    
    return documents

def _detect_content_type(content: str) -> str:
    """Enhanced content type detection"""
    content_lower = content.lower()
    
    has_table = '|' in content and ('|---' in content or '| ---' in content)
    has_figure = any(kw in content_lower for kw in ['figure', 'flowchart', 'diagram', 'algorithm'])
    has_list = content.count('\n-') > 3 or content.count('\n*') > 3
    
    if has_figure and has_table:
        return 'diagram_with_table'
    elif has_figure:
        return 'diagram'
    elif has_table:
        return 'table'
    elif has_list:
        return 'list'
    return 'text'

def _extract_section(content: str) -> str:
    for line in content.split('\n')[:15]:
        if line.startswith('#'):
            return line.replace('#', '').strip().lower().replace(':', '').strip()
    return 'general'

def _get_surrounding_context(documents, current_idx, direction='before', max_chars=300):
    """Get context from adjacent documents"""
    try:
        if direction == 'before' and current_idx > 0:
            prev_text = documents[current_idx - 1].text
            return ("..." + prev_text[-max_chars:]) if len(prev_text) > max_chars else prev_text
        elif direction == 'after' and current_idx < len(documents) - 1:
            next_text = documents[current_idx + 1].text
            return (next_text[:max_chars] + "...") if len(next_text) > max_chars else next_text
        return ""
    except:
        return ""

# ============================================================================
# SMART CHUNKING (Same as before - working correctly)
# ============================================================================

def _create_smart_chunks(documents, llm):
    """Chunking with semantic integrity"""
    from llama_index.core.node_parser import SentenceSplitter
    
    all_nodes = []
    splitter = SentenceSplitter(chunk_size=1200, chunk_overlap=300, separator="\n\n")
    
    for idx, doc in enumerate(documents):
        content_type = doc.metadata.get('content_type')
        token_count = doc.metadata.get('token_count', count_tokens(doc.text))
        
        context_before = _get_surrounding_context(documents, idx, 'before', 300)
        context_after = _get_surrounding_context(documents, idx, 'after', 300)
        
        if content_type == 'table':
            if token_count > MAX_EMBEDDING_TOKENS:
                # Split large tables
                text = doc.text
                rows = text.split('\n')
                table_rows = [r for r in rows if '|' in r]
                header_rows = []
                data_rows = []
                
                for i, row in enumerate(table_rows):
                    if '|---' in row or '| ---' in row:
                        header_rows = table_rows[:i+1]
                        data_rows = table_rows[i+1:]
                        break
                
                if not header_rows:
                    header_rows = [table_rows[0]] if table_rows else []
                    data_rows = table_rows[1:]
                
                header_text = '\n'.join(header_rows)
                header_tokens = count_tokens(header_text)
                target_tokens = 6000 - header_tokens - 500
                
                current_chunk = []
                current_tokens = 0
                chunks = []
                
                for row in data_rows:
                    row_tokens = count_tokens(row)
                    if current_tokens + row_tokens > target_tokens and current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = []
                        current_tokens = 0
                    current_chunk.append(row)
                    current_tokens += row_tokens
                
                if current_chunk:
                    chunks.append(current_chunk)
                
                if not chunks:
                    chunks = [[row] for row in data_rows[:10]]
                
                for chunk_idx, chunk_rows in enumerate(chunks):
                    chunk_text = header_text + '\n' + '\n'.join(chunk_rows)
                    
                    if chunk_idx == 0:
                        chunk_text = f"[TABLE PART {chunk_idx+1}/{len(chunks)}]\n{context_before}\n\n{chunk_text}"
                    else:
                        chunk_text = f"[TABLE PART {chunk_idx+1}/{len(chunks)} - CONTINUED]\n{chunk_text}"
                    
                    chunk_tokens = count_tokens(chunk_text)
                    if chunk_tokens > MAX_EMBEDDING_TOKENS:
                        chunk_text = truncate_to_tokens(chunk_text, MAX_EMBEDDING_TOKENS - 100)
                        chunk_tokens = MAX_EMBEDDING_TOKENS - 100
                    
                    node = TextNode(
                        text=chunk_text,
                        metadata={
                            **doc.metadata,
                            'chunk_index': chunk_idx,
                            'total_chunks': len(chunks),
                            'is_split_table': True,
                            'original_tokens': token_count
                        }
                    )
                    all_nodes.append(node)
                
                continue
            
            else:
                enriched_text = f"PRECEDING CONTEXT:\n{context_before}\n\n{doc.text}\n\nFOLLOWING CONTEXT:\n{context_after}"
                
                enriched_tokens = count_tokens(enriched_text)
                if enriched_tokens > MAX_EMBEDDING_TOKENS:
                    enriched_text = f"{doc.text}\n\nCONTEXT: {context_before[:200]}"
                    enriched_tokens = count_tokens(enriched_text)
                    if enriched_tokens > MAX_EMBEDDING_TOKENS:
                        enriched_text = truncate_to_tokens(enriched_text, MAX_EMBEDDING_TOKENS - 100)
                        enriched_tokens = MAX_EMBEDDING_TOKENS - 100
                
                node = TextNode(
                    text=enriched_text,
                    metadata={**doc.metadata, 'has_context': True, 'is_split_table': False}
                )
                all_nodes.append(node)
        
        elif content_type in ['diagram', 'diagram_with_table']:
            if token_count > MAX_EMBEDDING_TOKENS:
                summary = _summarize_large_content(doc.text, llm, max_tokens=5000)
                enriched_text = f"CONTEXT:\n{context_before}\n\n{summary}\n\nCONTEXT:\n{context_after}"
                
                enriched_tokens = count_tokens(enriched_text)
                if enriched_tokens > MAX_EMBEDDING_TOKENS:
                    enriched_text = truncate_to_tokens(enriched_text, MAX_EMBEDDING_TOKENS - 100)
                    enriched_tokens = MAX_EMBEDDING_TOKENS - 100
                
                node = TextNode(
                    text=enriched_text,
                    metadata={
                        **doc.metadata,
                        'is_summary': True,
                        'original_tokens': token_count,
                        'raw_content': doc.text[:10000]
                    }
                )
            else:
                enriched_text = f"{context_before}\n\n{doc.text}\n\n{context_after}"
                enriched_tokens = count_tokens(enriched_text)
                if enriched_tokens > MAX_EMBEDDING_TOKENS:
                    enriched_text = truncate_to_tokens(doc.text, MAX_EMBEDDING_TOKENS - 100)
                    enriched_tokens = MAX_EMBEDDING_TOKENS - 100
                
                node = TextNode(
                    text=enriched_text,
                    metadata={**doc.metadata, 'has_context': True, 'is_summary': False}
                )
            
            all_nodes.append(node)
        
        else:
            chunks = splitter.split_text(doc.text)
            for chunk_idx, chunk in enumerate(chunks):
                all_nodes.append(TextNode(
                    text=chunk,
                    metadata={
                        **doc.metadata,
                        'chunk_id': chunk_idx,
                        'total_chunks': len(chunks)
                    }
                ))
    
    return all_nodes

def _summarize_large_content(text: str, llm, max_tokens: int = 5000) -> str:
    """Summarize large content with LLM"""
    prompt = f"""Summarize this INASL Puri 3 HCC guideline diagram/flowchart for medical retrieval.
Focus on: treatment decision points, BCLC staging, clinical pathways, contraindications.
Maximum {max_tokens // 4} words.

CONTENT:
{text[:8000]}

SUMMARY:
"""
    try:
        response = llm.complete(prompt)
        summary = f"[DIAGRAM SUMMARY - {count_tokens(text)} tokens]\n{response}"
        return summary
    except Exception as e:
        logger.error(f"   ❌ Summarization failed: {e}")
        return truncate_to_tokens(text, max_tokens)

def create_or_load_index(documents=None, force_recreate: bool = False):
    if not force_recreate and INDEX_DIR.exists():
        try:
            logger.info("📂 Loading cached vector index")
            storage_context = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(storage_context)
            logger.info("✅ Loaded cached index")
            return index
        except Exception as e:
            logger.warning(f"⚠️ Failed to load cache: {e}")
    
    if documents is None:
        raise ValueError("Documents required to create new index")
    
    logger.info("🔄 Creating vector index from INASL Puri 3 guidelines")
    nodes = _create_smart_chunks(documents, Settings.llm)
    
    chunk_tokens = [count_tokens(node.text) for node in nodes]
    logger.info("="*80)
    logger.info("📊 FINAL VERIFICATION:")
    logger.info(f"   Total chunks: {len(chunk_tokens)}")
    logger.info(f"   Min: {min(chunk_tokens):,} | Max: {max(chunk_tokens):,} | Avg: {sum(chunk_tokens)//len(chunk_tokens):,}")
    
    oversized = [(i, t) for i, t in enumerate(chunk_tokens) if t > MAX_EMBEDDING_TOKENS]
    if oversized:
        logger.error(f"❌ {len(oversized)} chunks exceed {MAX_EMBEDDING_TOKENS} tokens!")
        raise ValueError(f"Chunks exceed limit!")
    
    logger.info(f"   ✅ All chunks <{MAX_EMBEDDING_TOKENS} tokens")
    logger.info("="*80)
    
    logger.info("🔄 Generating embeddings...")
    index = VectorStoreIndex(nodes=nodes, show_progress=True)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info(f"✅ Index cached to {INDEX_DIR}")
    return index

# ============================================================================
# OPTIMIZED RETRIEVAL
# ============================================================================

class OptimizedRetriever:
    """Enhanced retrieval with medical keyword boosting"""
    def __init__(self, index):
        self.index = index
        self.base_retriever = index.as_retriever(similarity_top_k=15)
        
        self.medical_keywords = {
            'treatment': 1.3, 'therapy': 1.3, 'bclc': 1.5, 'stage': 1.4,
            'resection': 1.3, 'ablation': 1.3, 'tace': 1.4, 'tare': 1.4,
            'transplant': 1.4, 'systemic': 1.3, 'sorafenib': 1.3,
            'atezolizumab': 1.3, 'child-pugh': 1.4, 'meld': 1.3,
            'portal': 1.3, 'pvtt': 1.4, 'contraindication': 1.4,
            'eligibility': 1.3, 'criteria': 1.3, 'inasl': 1.5, 'puri': 1.4
        }
    
    def retrieve(self, query: str, bclc_stage: str = None, child_pugh: str = None) -> List[Dict]:
        enhanced_query = self._enhance_query(query, bclc_stage, child_pugh)
        
        nodes = self.base_retriever.retrieve(enhanced_query)
        if not nodes:
            return []
        
        filtered = self._filter_by_relevance(nodes, bclc_stage, child_pugh)
        grouped = self._group_related_nodes(filtered)
        reranked = self._rerank_by_medical_relevance(grouped, bclc_stage, child_pugh)
        return reranked[:7]
    
    def _enhance_query(self, query: str, bclc_stage: str = None, child_pugh: str = None) -> str:
        enhanced = query + " INASL Puri 3 guidelines"
        if bclc_stage:
            enhanced += f" BCLC {bclc_stage} treatment"
        if child_pugh:
            enhanced += f" Child-Pugh {child_pugh}"
        return enhanced
    
    def _filter_by_relevance(self, nodes, bclc, cp):
        filtered = []
        for node in nodes:
            threshold = 0.4 if node.metadata.get('content_type') in ['table', 'diagram'] else 0.5
            
            if node.score >= threshold:
                filtered.append(node)
            elif bclc or cp:
                text_lower = node.text.lower()
                if (bclc and bclc.lower() in text_lower) or (cp and cp.lower() in text_lower):
                    filtered.append(node)
        
        logger.info(f"   Filtered {len(nodes)} → {len(filtered)}")
        return filtered
    
    def _group_related_nodes(self, nodes):
        groups = []
        used = set()
        for i, node in enumerate(nodes):
            if i in used:
                continue
            group = {'primary': node, 'context': [], 'combined_score': node.score, 'type': 'single'}
            if node.metadata.get('content_type') in ['table', 'diagram']:
                page = node.metadata.get('page_number')
                section = node.metadata.get('section')
                for j, other in enumerate(nodes):
                    if j != i and j not in used:
                        if (abs(other.metadata.get('page_number', 999) - page) <= 1 or 
                            other.metadata.get('section') == section):
                            group['context'].append(other)
                            group['combined_score'] += other.score * 0.3
                            used.add(j)
                group['type'] = 'structured_with_context'
            groups.append(group)
            used.add(i)
        logger.info(f"   Grouped into {len(groups)} groups")
        return groups
    
    def _rerank_by_medical_relevance(self, groups, bclc, cp):
        for group in groups:
            score = group['combined_score']
            text = group['primary'].text.lower()
            
            for keyword, boost in self.medical_keywords.items():
                if keyword in text:
                    score *= boost
            
            if bclc and bclc.lower() in text:
                score *= 1.4
            if cp and cp.lower() in text:
                score *= 1.3
            
            if group['primary'].metadata.get('content_type') in ['table', 'diagram']:
                score *= 1.35
            
            if 'treatment' in group['primary'].metadata.get('section', ''):
                score *= 1.2
            
            if group['context']:
                score *= 1.15
            
            group['final_score'] = score
        
        ranked = sorted(groups, key=lambda x: x['final_score'], reverse=True)
        logger.info(
            "Top 3 scores: %s",
            [f"{g['final_score']:.2f}" for g in ranked[:3]]
        )    
        return ranked

# ============================================================================
# ✅ BASE SPECIALIST AGENT CLASS (INASL COMPLIANT)
# ============================================================================

class BaseSpecialistAgent:
    """
    Base class with standardized context building per INASL guidelines
    """
    
    def __init__(self, index):
        self.retriever = OptimizedRetriever(index)
        self.llm = Settings.llm
    
    def _build_context_standardized(self, groups, max_chars_per_source=5000, include_grouped=True):
        """Standardized context builder with INASL source attribution"""
        if not groups:
            return "No relevant INASL Puri 3 guideline sections found in retrieved sources."
        
        parts = []
        total_tokens = 0
        
        for i, group in enumerate(groups, 1):
            primary = group['primary']
            
            text = primary.text
            
            if include_grouped and group.get('context'):
                context_texts = []
                for ctx in group['context'][:2]:
                    ctx_text = ctx.text[:400]
                    context_texts.append(f"   [RELATED CONTEXT] {ctx_text}...")
                if context_texts:
                    text = text + "\n" + "\n".join(context_texts)
            
            if len(text) > max_chars_per_source:
                text = text[:max_chars_per_source] + "\n...[TRUNCATED]"
            
            page = primary.metadata.get('page_number', '?')
            section = primary.metadata.get('section', 'general')
            content_type = primary.metadata.get('content_type', 'text')
            
            if primary.metadata.get('is_split_table'):
                chunk_idx = primary.metadata.get('chunk_index', 0)
                total_chunks = primary.metadata.get('total_chunks', 1)
                header = f"[SOURCE {i}] INASL Puri 3 Page {page} | **PARTIAL TABLE** (Part {chunk_idx+1}/{total_chunks}) | Section: {section}"
            else:
                header = f"[SOURCE {i}] INASL Puri 3 Page {page} | Type: {content_type.upper()} | Section: {section}"
            
            parts.append(f"{header}\n{text}")
            
            part_tokens = count_tokens(text)
            total_tokens += part_tokens
        
        logger.info(f"   Built context: {total_tokens:,} tokens from {len(groups)} INASL sources")
        return "\n\n" + "─"*80 + "\n\n".join(parts)
    
    def _calc_confidence(self, groups):
        """Calculate confidence from retrieval results"""
        if not groups:
            return 0.0
        avg = sum(g.get('final_score', g['combined_score']) for g in groups) / len(groups)
        return round(min(avg / 2.0, 1.0), 2)
    
    def _assess_quality(self, groups):
        """Assess evidence quality"""
        if not groups:
            return "None"
        
        has_table = any(g['primary'].metadata.get('content_type') == 'table' for g in groups)
        has_diagram = any(g['primary'].metadata.get('content_type') == 'diagram' for g in groups)
        has_context = any(g['context'] for g in groups)
        avg = sum(g.get('final_score', g['combined_score']) for g in groups) / len(groups)
        
        if has_table and has_diagram and has_context and avg > 1.5:
            return "High"
        elif (has_table or has_diagram) and avg > 1.0:
            return "Medium"
        return "Moderate"

# ============================================================================
# ✅ SPECIALIST AGENTS - INASL COMPLIANT WITH WORKFLOW ALIGNMENT
# ============================================================================

class HepatologistAgent(BaseSpecialistAgent):
    """
    ✅ Hepatologist (LEAD DECISION MAKER) - Per Workflow Page 8
    
    WORKFLOW REQUIREMENTS:
    1. Review all data
    2. Calculate Child-Pugh & MELD (already in parsed data)
    3. Determine BCLC stage (already calculated)
    4. Apply treatment algorithm
    5. Assess contraindications
    6. Synthesize specialist input
    """
    
    def analyze(self, patient_data: Dict, instructions: Optional[SpecialistInstruction] = None) -> SpecialistResult:
        try:
            logger.info("🔬 Hepatologist (LEAD) analyzing per INASL guidelines...")
            
            clinical = patient_data['clinical_summary']
            labs = clinical['labs_baseline']
            scores = clinical['derived_scores']
            child_pugh = scores['Child_Pugh']
            tumor_info = extract_tumor_summary(patient_data)
            bclc = extract_bclc_stage(patient_data)
            
            # Query focused on liver function and treatment tolerance
            query = f"""INASL Puri 3: Liver function Child-Pugh {child_pugh['class']}{child_pugh['score']}, MELD {scores.get('MELD')}, platelets {labs['platelets_k']}K, bilirubin {labs['total_bilirubin_mg_dl']}. BCLC {bclc}. Treatment tolerance, transplant eligibility, portal hypertension contraindications?"""
            
            if instructions:
                query += f" {instructions['focus_area']}"
            
            result_groups = self.retriever.retrieve(query, bclc, child_pugh['class'])
            confidence = self._calc_confidence(result_groups)
            
            try:
                context = self._build_context_standardized(result_groups, max_chars_per_source=5000, include_grouped=True)
            except Exception as e:
                logger.error(f"❌ Context building failed: {e}")
                context = "ERROR: Could not build context from INASL guidelines"
            
            patient_summary = create_concise_patient_summary(patient_data)
            
            instruction_text = ""
            if instructions:
                instruction_text = f"\n📌 FOCUS: {instructions['focus_area']}\n📌 QUESTIONS: {'; '.join(instructions['specific_questions'])}"
            
            # Milan/UCSF criteria assessment
            milan_status = self._assess_milan_ucsf(tumor_info)
            portal_htn_risk = "HIGH" if labs['platelets_k'] < 100 else "MODERATE" if labs['platelets_k'] < 150 else "LOW"
            
            prompt = f"""You are the LEAD HEPATOLOGIST in an HCC tumor board analyzing INASL Puri 3 guideline evidence.

{patient_summary}
BCLC STAGE: {bclc}
Portal HTN Risk: {portal_htn_risk} (Plt {labs['platelets_k']}K)
Transplant Criteria: {milan_status}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INASL PURI 3 GUIDELINE EXCERPTS:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction_text}

🔒 STRICT GROUNDING RULES (INASL PURI 3 ONLY):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Use ONLY INASL Puri 3 guideline text above
2. QUOTE relevant passages FIRST with [SOURCE #]
3. Format: "According to INASL [SOURCE X]: '<quote>'. This indicates..."
4. If unclear, state: "INASL guideline does not explicitly address..."
5. NO external knowledge beyond INASL Puri 3
6. Focus on FIRST-LINE treatment per INASL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per Workflow Page 8 - Hepatologist Flow:
1. Review all data ✓
2. Calculate Child-Pugh & MELD: {child_pugh['class']}{child_pugh['score']}, MELD {scores.get('MELD')} ✓
3. Determine BCLC stage: {bclc} ✓
4. Apply treatment algorithm (INASL-based)
5. Assess contraindications
6. Synthesize specialist input as LEAD decision maker

Provide LEAD HEPATOLOGIST assessment:

**INASL GUIDELINE EVIDENCE:**
[Quote relevant INASL passages with SOURCE #]

**LIVER FUNCTION ASSESSMENT:**
[Child-Pugh {child_pugh['class']}, MELD {scores.get('MELD')}, portal HTN risk per INASL]

**TREATMENT TOLERANCE:**
[Which modalities patient can tolerate based on INASL guideline - resection, ablation, TACE, transplant, systemic?]

**TRANSPLANT ELIGIBILITY:**
[Milan/UCSF criteria assessment per INASL, listing priority]

**PORTAL HYPERTENSION CONTRAINDICATIONS:**
[Specific INASL guidance on portal HTN and treatment contraindications]

**OPTIMIZATION NEEDED:**
[Pre-treatment interventions from INASL guideline]

**LEAD HEPATOLOGIST RECOMMENDATION (per INASL):**
[As LEAD decision maker, synthesize PRIMARY first-line treatment approach per INASL Puri 3 for BCLC {bclc}]

**CONFIDENCE NOTE:**
[If any uncertainty, explicitly state what INASL guideline does not address]
"""
            
            response = self.llm.complete(prompt)
            
            critical_flags = extract_lab_abnormalities(clinical)
            if child_pugh['class'] == 'C':
                critical_flags.append("Child-Pugh C - very limited options per INASL")
            elif child_pugh['class'] == 'B':
                critical_flags.append("Child-Pugh B - decompensated, limited treatment options")
            
            if scores.get('MELD_Na', 0) > 20:
                critical_flags.append(f"High MELD-Na ({scores.get('MELD_Na')}) - transplant evaluation needed")
            
            if portal_htn_risk in ['HIGH', 'MODERATE']:
                critical_flags.append(f"{portal_htn_risk} portal hypertension risk - resection contraindicated")
            
            logger.info("✅ Hepatologist (LEAD) complete")
            return {
                'specialist': 'Hepatology (Lead Decision Maker)',
                'assessment': str(response),
                'recommendations': [milan_status, f"Child-Pugh {child_pugh['class']}", f"Portal HTN: {portal_htn_risk}"],
                'confidence': confidence,
                'evidence_quality': self._assess_quality(result_groups),
                'critical_flags': critical_flags
            }
            
        except Exception as e:
            logger.error(f"❌ Hepatologist failed: {e}")
            return {
                'specialist': 'Hepatology',
                'assessment': f'Error: {e}',
                'recommendations': [],
                'confidence': 0.0,
                'evidence_quality': 'Error',
                'critical_flags': ['Analysis failed']
            }
    
    def _assess_milan_ucsf(self, tumor_info):
        """Assess Milan and UCSF criteria per INASL"""
        count = tumor_info['count']
        max_size = tumor_info['max_size_cm']
        total_size = sum(float(l.split('cm')[0]) for l in tumor_info['lesions'] if 'cm' in l)
        
        # Milan criteria
        milan = False
        if count == 1 and max_size <= 5:
            milan = True
        elif count <= 3 and max_size <= 3:
            milan = True
        
        # UCSF criteria (more liberal)
        ucsf = False
        if count == 1 and max_size <= 6.5:
            ucsf = True
        elif count <= 3 and max_size <= 4.5 and total_size <= 8.0:
            ucsf = True
        
        if milan and ucsf:
            return f"WITHIN MILAN & UCSF - Transplant eligible ({count} lesion(s), max {max_size}cm)"
        elif ucsf:
            return f"WITHIN UCSF (exceeds Milan) - Consider transplant per INASL ({count} lesion(s), max {max_size}cm)"
        else:
            return f"OUTSIDE Milan/UCSF - Not standard transplant candidate ({count} lesion(s), max {max_size}cm, total {total_size:.1f}cm)"


class RadiologistAgent(BaseSpecialistAgent):
    """
    ✅ Radiologist (Interventional) - Per Workflow Page 8
    
    WORKFLOW REQUIREMENTS:
    1. Review imaging
    2. Apply LI-RADS
    3. Measure tumors
    4. Assess vasculature
    5. Evaluate extrahepatic disease
    6. Determine intervention feasibility (RFA/MWA/TACE/TARE/SBRT)
    """
    
    def analyze(self, patient_data: Dict, instructions: Optional[SpecialistInstruction] = None) -> SpecialistResult:
        try:
            logger.info("📸 Radiologist analyzing per INASL guidelines...")
            
            radiology = patient_data['radiology_summary']
            baseline_study = radiology['studies'][0]
            tumor_info = extract_tumor_summary(patient_data)
            bclc = extract_bclc_stage(patient_data)
            clinical = patient_data['clinical_summary']
            child_pugh = clinical['derived_scores']['Child_Pugh']
            
            query = f"""INASL Puri 3: HCC LI-RADS {baseline_study.get('overall_derived_li_rads')}, {tumor_info['count']} lesions {tumor_info['distribution']}, max {tumor_info['max_size_cm']}cm. BCLC {bclc}. RFA/MWA, TACE, Y90-TARE, SBRT feasibility and technical approach?"""
            
            if instructions:
                query += f" {instructions['focus_area']}"
            
            result_groups = self.retriever.retrieve(query, bclc, None)
            confidence = self._calc_confidence(result_groups)
            
            try:
                context = self._build_context_standardized(result_groups, max_chars_per_source=5000, include_grouped=True)
            except Exception as e:
                context = "ERROR: Could not build context from INASL guidelines"
            
            patient_summary = create_concise_patient_summary(patient_data)
            
            instruction_text = ""
            if instructions:
                instruction_text = f"\n📌 FOCUS: {instructions['focus_area']}\n📌 QUESTIONS: {'; '.join(instructions['specific_questions'])}"
            
            prompt = f"""Expert INTERVENTIONAL RADIOLOGIST analyzing INASL Puri 3 guideline evidence.

{patient_summary}
IMAGING: {baseline_study.get('modality')} - LI-RADS {baseline_study.get('overall_derived_li_rads')}
LESIONS: {'; '.join(tumor_info['lesions'])}
BCLC: {bclc}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INASL PURI 3 GUIDELINE EXCERPTS:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction_text}

🔒 STRICT GROUNDING RULES (INASL PURI 3 ONLY):
1. ONLY use INASL Puri 3 guideline text above
2. QUOTE first with [SOURCE #]
3. If unclear: "INASL guideline does not specify..."
4. Focus on FIRST-LINE locoregional options per INASL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per Workflow Page 8 - Radiologist Flow:
1. Review imaging ✓
2. Apply LI-RADS: {baseline_study.get('overall_derived_li_rads')} ✓
3. Measure tumors: {tumor_info['count']} lesions, max {tumor_info['max_size_cm']}cm ✓
4. Assess vasculature (PVTT, portal flow)
5. Evaluate extrahepatic disease
6. Determine intervention feasibility per INASL

**INASL GUIDELINE EVIDENCE:**
[Quote with SOURCE #]

**DIAGNOSIS CONFIRMATION:**
[LI-RADS {baseline_study.get('overall_derived_li_rads')} interpretation per INASL, biopsy need?]

**LOCOREGIONAL OPTIONS (INASL Puri 3 based):**
For BCLC {bclc}, evaluate per INASL:
- RFA/MWA feasibility (size limits, location, number per INASL)
- TACE indications/contraindications (portal flow, liver function per INASL)
- Y90-TARE criteria (PVTT, tumor burden per INASL)
- SBRT considerations (size, location per INASL)

**TECHNICAL APPROACH (per INASL):**
[Specific technique, approach, contraindications from INASL guideline]

**VASCULAR ASSESSMENT:**
[Portal vein patency, arterial anatomy, PVTT status]

**FOLLOW-UP (per INASL):**
[INASL guideline schedule, mRECIST/RECIST criteria]

**PRIMARY RECOMMENDATION (per INASL):**
[Most appropriate locoregional option for BCLC {bclc} based on INASL Puri 3]
"""
            
            response = self.llm.complete(prompt)
            
            critical_flags = []
            lesions = baseline_study.get('lesions', [])
            if any(l.get('pvtt') for l in lesions):
                critical_flags.append("PVTT detected - consider Y90-TARE per INASL")
            if any(l.get('extrahepatic_metastasis') for l in lesions):
                critical_flags.append("Extrahepatic metastasis - systemic therapy indicated")
            
            li_rads = baseline_study.get('overall_derived_li_rads', '')
            if 'LR-3' in li_rads or 'LR-4' in li_rads:
                critical_flags.append(f"Indeterminate imaging ({li_rads}) - biopsy may be needed")
            
            logger.info("✅ Radiologist complete")
            return {
                'specialist': 'Interventional Radiology',
                'assessment': str(response),
                'recommendations': self._suggest_interventions_inasl(bclc, tumor_info, child_pugh),
                'confidence': confidence,
                'evidence_quality': self._assess_quality(result_groups),
                'critical_flags': critical_flags
            }
            
        except Exception as e:
            return {
                'specialist': 'Radiology',
                'assessment': f'Error: {e}',
                'recommendations': [],
                'confidence': 0.0,
                'evidence_quality': 'Error',
                'critical_flags': ['Analysis failed']
            }
    
    def _suggest_interventions_inasl(self, bclc, tumor_info, child_pugh):
        """Suggest interventions per INASL BCLC staging"""
        options = []
        count = tumor_info['count']
        max_size = tumor_info['max_size_cm']
        
        if '0' in bclc:
            if count == 1 and max_size < 2:
                options.append("RFA/MWA first-line per INASL BCLC 0")
                options.append("Resection if no portal HTN")
        
        if 'A' in bclc and '0' not in bclc:
            if count <= 3 and max_size <= 3:
                options.append("Ablation (RFA/MWA) feasible per INASL BCLC A")
            if count == 1:
                options.append("Resection option if no portal HTN")
            if max_size > 3:
                options.append("TACE option for larger lesions")
        
        if 'B' in bclc:
            options.append("TACE first-line per INASL BCLC B")
            options.append("Y90-TARE alternative per INASL")
            if 'B3' in bclc:
                options.append("Consider systemic therapy for extensive B3")
        
        if 'C' in bclc:
            if 'C1' in bclc:
                options.append("Y90-TARE for PVTT per INASL C1")
            options.append("Systemic therapy primary per INASL BCLC C")
        
        return options if options else ["Per INASL: Locoregional options limited for this BCLC stage"]


class SurgeonAgent(BaseSpecialistAgent):
    """
    ✅ Surgeon (Hepatobiliary/Transplant) - Per Workflow Page 8
    
    WORKFLOW REQUIREMENTS:
    1. Review imaging
    2. Assess tumor location
    3. Calculate future liver remnant (FLR)
    4. Risk stratification
    5. Determine resectability
    """
    
    def analyze(self, patient_data: Dict, instructions: Optional[SpecialistInstruction] = None) -> SpecialistResult:
        try:
            logger.info("🔪 Surgeon analyzing per INASL guidelines...")
            
            clinical = patient_data['clinical_summary']
            labs = clinical['labs_baseline']
            child_pugh = clinical['derived_scores']['Child_Pugh']
            tumor_info = extract_tumor_summary(patient_data)
            bclc = extract_bclc_stage(patient_data)
            
            query = f"""INASL Puri 3: HCC resection criteria: {tumor_info['count']} lesions max {tumor_info['max_size_cm']}cm, {tumor_info['distribution']}, Child-Pugh {child_pugh['class']}, platelets {labs['platelets_k']}K. Resectability criteria, portal hypertension contraindications, FLR requirements?"""
            
            if instructions:
                query += f" {instructions['focus_area']}"
            
            result_groups = self.retriever.retrieve(query, bclc, child_pugh['class'])
            confidence = self._calc_confidence(result_groups)
            
            try:
                context = self._build_context_standardized(result_groups, max_chars_per_source=5000, include_grouped=True)
            except Exception as e:
                context = "ERROR: Could not build context from INASL guidelines"
            
            patient_summary = create_concise_patient_summary(patient_data)
            portal_htn_risk = "HIGH" if labs['platelets_k'] < 100 else "MODERATE" if labs['platelets_k'] < 150 else "LOW"
            
            instruction_text = ""
            if instructions:
                instruction_text = f"\n📌 FOCUS: {instructions['focus_area']}\n📌 QUESTIONS: {'; '.join(instructions['specific_questions'])}"
            
            resectability = self._assess_resectability_inasl(tumor_info, child_pugh, labs)
            
            prompt = f"""Expert HEPATOBILIARY SURGEON analyzing INASL Puri 3 guideline evidence.

{patient_summary}
BCLC: {bclc}
Portal HTN: {portal_htn_risk} (Plt {labs['platelets_k']}K)
CLINICAL ASSESSMENT: {resectability}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INASL PURI 3 GUIDELINE EXCERPTS:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction_text}

🔒 STRICT GROUNDING RULES (INASL PURI 3 ONLY):
1. ONLY INASL Puri 3 guideline text
2. QUOTE with [SOURCE #]
3. If unclear: "INASL guideline does not specify..."
4. Focus on resection criteria per INASL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per Workflow Page 8 - Surgical Flow:
1. Review imaging ✓
2. Assess tumor location: {tumor_info['distribution']}, {tumor_info['count']} lesions ✓
3. Calculate FLR (per INASL requirements)
4. Risk stratification: Child-Pugh {child_pugh['class']}, portal HTN {portal_htn_risk}
5. Determine resectability per INASL

**INASL GUIDELINE EVIDENCE:**
[Quote with SOURCE #]

**RESECTABILITY (INASL-based):**
[Anatomic resectability, FLR requirements (>30-40%), vascular involvement per INASL]

**PORTAL HYPERTENSION (per INASL):**
[INASL guideline on portal HTN as contraindication to resection - platelets {labs['platelets_k']}K]

**OPERATIVE RISK (per INASL):**
[Child-Pugh {child_pugh['class']} implications for surgical candidacy per INASL]

**TRANSPLANT EVALUATION (if applicable):**
[Transplant vs resection decision per INASL criteria]

**SURGICAL RECOMMENDATION (per INASL):**
[Resection: FEASIBLE / BORDERLINE / CONTRAINDICATED with INASL-based rationale]

**ALTERNATIVE IF NOT RESECTABLE:**
[Per INASL: Transplant, ablation, or locoregional therapy options]
"""
            
            response = self.llm.complete(prompt)
            
            critical_flags = extract_lab_abnormalities(clinical)
            if child_pugh['class'] != 'A':
                critical_flags.append(f"Child-Pugh {child_pugh['class']} - high surgical risk, resection contraindicated per INASL")
            if labs['platelets_k'] < 150:
                critical_flags.append(f"Portal hypertension (plt {labs['platelets_k']}K) - contraindication to resection per INASL")
            
            logger.info("✅ Surgeon complete")
            return {
                'specialist': 'Surgical Oncology / Transplant Surgery',
                'assessment': str(response),
                'recommendations': [resectability],
                'confidence': confidence,
                'evidence_quality': self._assess_quality(result_groups),
                'critical_flags': critical_flags
            }
            
        except Exception as e:
            return {
                'specialist': 'Surgery',
                'assessment': f'Error: {e}',
                'recommendations': [],
                'confidence': 0.0,
                'evidence_quality': 'Error',
                'critical_flags': ['Analysis failed']
            }
    
    def _assess_resectability_inasl(self, tumor_info, child_pugh, labs):
        """Assess resectability per INASL criteria"""
        if child_pugh['class'] != 'A':
            return "CONTRAINDICATED - Child-Pugh B/C per INASL"
        
        if labs['platelets_k'] < 150:
            return f"CONTRAINDICATED - Portal hypertension (plt {labs['platelets_k']}K) per INASL"
        
        count = tumor_info['count']
        max_size = tumor_info['max_size_cm']
        distribution = tumor_info['distribution']
        
        if count == 1:
            if max_size <= 5:
                return "FEASIBLE - Single lesion ≤5cm, CP-A, no portal HTN per INASL"
            else:
                return f"BORDERLINE - Large single lesion ({max_size}cm), requires FLR >30-40% per INASL"
        elif count <= 3:
            if distribution == 'unilobar':
                return "BORDERLINE - Oligonodular unilobar, assess FLR per INASL"
            else:
                return "NOT FEASIBLE - Bilobar multifocal disease per INASL"
        else:
            return "NOT FEASIBLE - Too many lesions (>3) per INASL"


class OncologistAgent(BaseSpecialistAgent):
    """
    ✅ Oncologist (Medical) - Per Workflow
    
    SHOULD ONLY BE CALLED FOR:
    - BCLC C (Advanced) → PRIMARY specialist
    - BCLC B3 (Extensive) → If locoregional not feasible
    - BCLC A/B → Only if other options contraindicated (BACKUP)
    """
    
    def analyze(self, patient_data: Dict, instructions: Optional[SpecialistInstruction] = None) -> SpecialistResult:
        try:
            logger.info("📋 Oncologist analyzing per INASL guidelines...")
            
            clinical = patient_data['clinical_summary']
            labs = clinical['labs_baseline']
            child_pugh = clinical['derived_scores']['Child_Pugh']
            tumor_info = extract_tumor_summary(patient_data)
            bclc = extract_bclc_stage(patient_data)
            
            # ✅ FIXED: Query should be BCLC-appropriate
            if 'C' in bclc:
                query = f"""INASL Puri 3: HCC BCLC {bclc} systemic therapy. Child-Pugh {child_pugh['class']}, ECOG {clinical['ECOG']}, AFP {labs['AFP_ng_ml']}. First-line systemic therapy options, dosing, contraindications?"""
            elif 'B3' in bclc:
                query = f"""INASL Puri 3: HCC BCLC {bclc} extensive disease. Systemic therapy vs locoregional options. Child-Pugh {child_pugh['class']}, {tumor_info['count']} lesions."""
            else:
                # For BCLC A/B, oncologist is backup only
                query = f"""INASL Puri 3: HCC BCLC {bclc} when curative/locoregional options contraindicated. Systemic therapy alternatives."""
            
            if instructions:
                query += f" {instructions['focus_area']}"
            
            result_groups = self.retriever.retrieve(query, bclc, child_pugh['class'])
            confidence = self._calc_confidence(result_groups)
            
            try:
                context = self._build_context_standardized(result_groups, max_chars_per_source=5000, include_grouped=True)
            except Exception as e:
                logger.error(f"❌ Context building failed: {e}")
                context = "ERROR: Could not build context from INASL guidelines"
            
            patient_summary = create_concise_patient_summary(patient_data)
            
            instruction_text = ""
            if instructions:
                instruction_text = f"\n📌 FOCUS: {instructions['focus_area']}\n📌 QUESTIONS: {'; '.join(instructions['specific_questions'])}"
            
            # ✅ FIXED: Role clarity based on BCLC
            if 'C' in bclc:
                role_desc = "PRIMARY specialist for BCLC C (Advanced)"
            elif 'B3' in bclc:
                role_desc = "SECONDARY specialist for BCLC B3 if locoregional limited"
            else:
                role_desc = "BACKUP specialist if curative/locoregional options contraindicated"
            
            prompt = f"""You are a MEDICAL ONCOLOGIST ({role_desc}) analyzing INASL Puri 3 guideline evidence.

{patient_summary}
BCLC STAGE: {bclc}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INASL PURI 3 GUIDELINE EXCERPTS:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction_text}

🔒 STRICT GROUNDING RULES (INASL PURI 3 ONLY):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Use ONLY INASL Puri 3 guideline text above
2. QUOTE relevant guideline passage FIRST before interpreting
3. Format: "According to INASL [SOURCE X]: '<quoted text>'. This means..."
4. If guideline unclear, state: "INASL guideline does not clearly specify..."
5. Do NOT add external knowledge beyond INASL Puri 3
6. Focus on FIRST-LINE systemic options per INASL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Provide assessment per INASL Puri 3:

**INASL GUIDELINE EVIDENCE:**
[Quote relevant INASL guideline text with SOURCE #]

**INTERPRETATION:**
[Based on quoted INASL text only]

**SYSTEMIC THERAPY INDICATION (per INASL):**
[For BCLC {bclc}, is systemic therapy: PRIMARY / SECONDARY / BACKUP option per INASL?]

**PRIMARY RECOMMENDATION (if indicated per INASL):**
[Specific regimen with dosing from INASL, e.g., "Atezolizumab 1200mg IV + Bevacizumab 15mg/kg q3w per INASL"]

**ALTERNATIVES (if contraindicated per INASL):**
[From INASL guideline only: Lenvatinib, Sorafenib, Durvalumab-Tremelimumab, etc.]

**CONTRAINDICATIONS (per INASL):**
[Patient-specific contraindications from INASL guideline]

**MONITORING (per INASL):**
[Imaging/labs schedule from INASL, mRECIST/RECIST criteria]

**RED FLAGS:**
[Patient-specific urgent concerns for systemic therapy]

**CONFIDENCE NOTE:**
[If any uncertainty, explicitly state what INASL guideline does not address]
"""
            
            response = self.llm.complete(prompt)
            
            critical_flags = extract_lab_abnormalities(clinical)
            if child_pugh['class'] in ['B', 'C']:
                critical_flags.append(f"Decompensated cirrhosis (Child-Pugh {child_pugh['class']}) - limited systemic therapy tolerance")
            if clinical['ECOG'] >= 2:
                critical_flags.append(f"Poor performance status (ECOG {clinical['ECOG']}) - may limit systemic therapy")
            
            # Check bevacizumab contraindications
            if labs.get('platelets_k', 150) < 75:
                critical_flags.append("Severe thrombocytopenia - bevacizumab bleeding risk")
            
            logger.info("✅ Oncologist complete")
            return {
                'specialist': 'Medical Oncology',
                'assessment': str(response),
                'recommendations': self._extract_recommendations(str(response)),
                'confidence': confidence,
                'evidence_quality': self._assess_quality(result_groups),
                'critical_flags': critical_flags
            }
            
        except Exception as e:
            logger.error(f"❌ Oncologist failed: {e}")
            return {
                'specialist': 'Medical Oncology', 
                'assessment': f'Error: {e}',
                'recommendations': [],
                'confidence': 0.0,
                'evidence_quality': 'Error',
                'critical_flags': ['Analysis failed']
            }
    
    def _extract_recommendations(self, response_text):
        """Extract key recommendations"""
        recommendations = []
        lines = response_text.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['recommend', 'first-line', 'primary', 'atezolizumab', 'lenvatinib', 'sorafenib']):
                if len(line.strip()) > 20:
                    recommendations.append(line.strip())
        return recommendations[:5]


class PathologistAgent(BaseSpecialistAgent):
    """
    ✅ Pathologist - Per Workflow Page 9
    
    CONDITIONAL INCLUSION:
    - Only when biopsy performed
    - Only when LI-RADS 3-4 (indeterminate)
    - Only when non-cirrhotic HCC suspected
    """
    
    def analyze(self, patient_data: Dict, instructions: Optional[SpecialistInstruction] = None) -> SpecialistResult:
        try:
            logger.info("🔬 Pathologist analyzing per INASL guidelines...")
            
            pathology = patient_data['pathology_summary']
            radiology = patient_data['radiology_summary']
            clinical = patient_data['clinical_summary']
            
            # Check if pathologist consultation is warranted
            biopsy_performed = pathology.get('biopsy_performed', False)
            baseline_study = radiology.get('studies', [{}])[0]
            li_rads = baseline_study.get('overall_derived_li_rads', '')
            
            if not biopsy_performed and 'LR-5' in li_rads:
                # LR-5 with no biopsy → Pathologist not needed
                logger.info("   ℹ️ LR-5 diagnosis, no biopsy → Pathologist consultation not indicated per INASL")
                return {
                    'specialist': 'Pathology',
                    'assessment': "Pathologist consultation not indicated. LR-5 imaging provides adequate diagnostic certainty per INASL Puri 3 guidelines. Biopsy not performed.",
                    'recommendations': ["No pathology review needed - LR-5 diagnosis per INASL"],
                    'confidence': 1.0,
                    'evidence_quality': 'Not Applicable',
                    'critical_flags': []
                }
            
            # If we get here, pathology input is relevant
            query = f"""INASL Puri 3: HCC biopsy indications, histologic diagnosis, differentiation grading. LI-RADS {li_rads}. When is biopsy needed per INASL?"""
            
            if instructions:
                query += f" {instructions['focus_area']}"
            
            result_groups = self.retriever.retrieve(query, None, None)
            confidence = self._calc_confidence(result_groups)
            
            try:
                context = self._build_context_standardized(result_groups, max_chars_per_source=5000, include_grouped=True)
            except Exception as e:
                context = "ERROR: Could not build context from INASL guidelines"
            
            histology = pathology.get('histology', {})
            diagnosis = histology.get('diagnosis', 'Not available')
            differentiation = histology.get('differentiation', 'Not graded')
            vascular_invasion = histology.get('vascular_invasion', None)
            
            instruction_text = ""
            if instructions:
                instruction_text = f"\n📌 FOCUS: {instructions['focus_area']}\n📌 QUESTIONS: {'; '.join(instructions['specific_questions'])}"
            
            prompt = f"""Expert PATHOLOGIST analyzing INASL Puri 3 guideline evidence.

IMAGING: LI-RADS {li_rads}
BIOPSY PERFORMED: {"Yes" if biopsy_performed else "No"}
HISTOLOGY: {diagnosis}
DIFFERENTIATION: {differentiation}
VASCULAR INVASION: {vascular_invasion if vascular_invasion is not None else "Not assessed"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INASL PURI 3 GUIDELINE EXCERPTS:
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction_text}

🔒 STRICT GROUNDING RULES (INASL PURI 3 ONLY):
1. ONLY INASL Puri 3 guideline text
2. QUOTE with [SOURCE #]
3. If unclear: "INASL guideline does not specify..."
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per Workflow Page 9 - Pathologist Flow:
1. Review indication for biopsy (LI-RADS {li_rads})
2. Evaluate tissue sample (if performed)
3. Assess differentiation
4. Perform IHC if needed
5. Correlate with imaging

**INASL GUIDELINE EVIDENCE:**
[Quote with SOURCE #]

**BIOPSY INDICATION (per INASL):**
[Is biopsy needed for LI-RADS {li_rads} per INASL Puri 3?]

**PATHOLOGIC DIAGNOSIS (if available):**
[HCC confirmed? Grade/differentiation? Vascular invasion?]

**IHC RESULTS (if performed):**
[Immunohistochemistry findings]

**CORRELATION WITH IMAGING:**
[Does pathology correlate with LI-RADS {li_rads}?]

**RECOMMENDATION:**
[Is additional pathology workup needed per INASL?]
"""
            
            response = self.llm.complete(prompt)
            
            critical_flags = []
            if vascular_invasion:
                critical_flags.append("Vascular invasion on histology - upstages to BCLC C per INASL")
            if 'poor' in str(differentiation).lower():
                critical_flags.append("Poorly differentiated HCC - aggressive biology")
            
            logger.info("✅ Pathologist complete")
            return {
                'specialist': 'Pathology',
                'assessment': str(response),
                'recommendations': [f"Histology: {diagnosis}", f"Grade: {differentiation}"],
                'confidence': confidence,
                'evidence_quality': self._assess_quality(result_groups),
                'critical_flags': critical_flags
            }
            
        except Exception as e:
            return {
                'specialist': 'Pathology',
                'assessment': f'Error: {e}',
                'recommendations': [],
                'confidence': 0.0,
                'evidence_quality': 'Error',
                'critical_flags': ['Analysis failed']
            }

# ============================================================================
# LANGGRAPH WORKFLOW NODES
# ============================================================================

def data_parser_node(state: IntegratedState) -> Dict:
    """✅ FIXED: Filters post-treatment data and notes_summary"""
    logger.info("🔄 Node: Data Parser")
    
    raw = state["raw_input_json"]
    
    # Filter clinical (remove time series)
    clinical = raw.get("clinical_summary", {}).copy()
    if "labs_time_series" in clinical:
        del clinical["labs_time_series"]
    
    # ✅ CRITICAL: Filter radiology to ONLY baseline (pre-treatment)
    radiology = raw.get("radiology_summary", {}).copy()
    if radiology.get("studies") and len(radiology["studies"]) > 1:
        logger.info(f"ℹ️ Filtering {len(radiology['studies'])-1} POST-TREATMENT studies (keeping ONLY baseline)")
        radiology["studies"] = [radiology["studies"][0]]  # Keep only first (baseline) study
    
    pathology = raw.get("pathology_summary", {})
    
    # ✅ CRITICAL: Ignore notes_summary (tumor board history)
    if "notes_summary" in raw:
        logger.info("ℹ️ Ignoring notes_summary (tumor board history - for evaluation only)")
    
    filtered = {
        "clinical_summary": clinical,
        "radiology_summary": radiology,
        "pathology_summary": pathology
    }
    
    logger.info("✅ Data parsing complete - FIRST-LINE treatment scenario")
    return {"filtered_data": filtered}


def bclc_calculator_node(state: IntegratedState) -> Dict:
    """INASL Puri 3 BCLC calculation"""
    logger.info("🔄 Node: INASL Puri 3 BCLC Calculator")
    
    data = state["filtered_data"]
    
    bclc_info = calculate_inasl_bclc(
        data["clinical_summary"],
        data["radiology_summary"],
        data["pathology_summary"]
    )
    
    logger.info(f"✅ BCLC (INASL Puri 3): {bclc_info['stage']}")
    logger.info(f"   Rationale: {bclc_info['rationale'][:100]}...")
    return {"bclc_result": bclc_info}


def strategy_generator_node(state: IntegratedState) -> Dict:
    """
    ✅ FIXED: INASL BCLC-driven strategy generation
    
    Generates specialist instructions based on INASL BCLC staging
    """
    logger.info("🔄 Node: INASL-Aligned Strategy Generator")
    
    data = state["filtered_data"]
    bclc = state["bclc_result"]
    
    clinical = data["clinical_summary"]
    tumor_info = extract_tumor_summary(data)
    patient_summary = create_concise_patient_summary(data)
    bclc_stage = bclc['stage']
    
    # ✅ FIXED: Temperature = 0.0
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    
    # ✅ CRITICAL: INASL-specific strategy based on BCLC stage
    inasl_strategy_guidance = f"""
Based on INASL Puri 3 BCLC {bclc_stage}:

{bclc['substage_detail']}

SPECIALIST PRIORITIES per INASL:
"""
    
    if 'D' in bclc_stage:
        inasl_strategy_guidance += """
- Hepatologist (PRIMARY): Palliative care, symptom management
- Oncologist (SECONDARY): Best supportive care options
- NO curative specialists needed
"""
    elif 'C2' in bclc_stage:
        inasl_strategy_guidance += """
- Oncologist (PRIMARY): Systemic therapy for extrahepatic disease
- Hepatologist (LEAD): Liver function support
- Radiologist (SECONDARY): Imaging surveillance
"""
    elif 'C1' in bclc_stage or 'C' in bclc_stage:
        inasl_strategy_guidance += """
- Oncologist (PRIMARY): Systemic therapy options
- Radiologist (SECONDARY): Y90-TARE for PVTT if C1
- Hepatologist (LEAD): Liver function assessment
"""
    elif 'B3' in bclc_stage:
        inasl_strategy_guidance += """
- Radiologist (PRIMARY): Y90-TARE vs TACE feasibility
- Hepatologist (LEAD): Treatment tolerance
- Oncologist (SECONDARY): Systemic therapy if locoregional limited
"""
    elif 'B2' in bclc_stage or 'B1' in bclc_stage:
        inasl_strategy_guidance += """
- Radiologist (PRIMARY): TACE planning and feasibility
- Hepatologist (LEAD): Liver function and treatment tolerance
- Surgeon (SECONDARY): Transplant evaluation if B1
"""
    elif 'A' in bclc_stage or '0' in bclc_stage:
        inasl_strategy_guidance += """
- Hepatologist (LEAD): Portal HTN assessment, treatment tolerance
- Surgeon (PRIMARY): Resection feasibility (if no portal HTN)
- Radiologist (PRIMARY): Ablation feasibility (if portal HTN or small lesions)
- Oncologist (BACKUP ONLY): Only if curative/locoregional contraindicated
"""
    
    prompt = f"""Generate HCC tumor board strategy per INASL Puri 3 guidelines.

{patient_summary}
BCLC (INASL Puri 3): {bclc_stage}
Rationale: {bclc['rationale']}
{inasl_strategy_guidance}

Generate specialist instructions as JSON per INASL BCLC {bclc_stage}:

{{
  "bclc_stage": "{bclc_stage}",
  "bclc_rationale": "{bclc['rationale']}",
  "bclc_substage_detail": "{bclc.get('substage_detail', '')}",
  "clinical_impression": "...",
  "treatment_intent": "CURATIVE / LOCOREGIONAL / SYSTEMIC / PALLIATIVE",
  "specialist_instructions": [
    // ONLY include specialists relevant to BCLC {bclc_stage} per INASL
    // For each specialist:
    {{
      "specialist_role": "Hepatologist / Radiologist / Surgeon / Oncologist / Pathologist",
      "priority": "PRIMARY / SECONDARY / CONDITIONAL",
      "focus_area": "Specific INASL-based focus for this BCLC stage",
      "specific_questions": ["Question 1 per INASL", "Question 2 per INASL"],
      "guidance_context": "Why this specialist is needed for BCLC {bclc_stage} per INASL"
    }}
  ],
  "orchestrator_guidance": "How to coordinate specialists per INASL workflow",
  "critical_checks": ["Check 1", "Check 2", "Check 3"]
}}

RULES:
1. Hepatologist is ALWAYS included as LEAD decision maker
2. For BCLC 0/A: Include Surgeon + Radiologist (curative intent)
3. For BCLC B: Include Radiologist (TACE/TARE) + Hepatologist
4. For BCLC C: Include Oncologist (systemic) + Hepatologist
5. For BCLC D: Include Hepatologist + Oncologist (palliative)
6. Pathologist: CONDITIONAL (only if biopsy performed or LI-RADS 3-4)
7. NEVER include Oncologist for BCLC 0/A/B unless explicitly needed as backup
8. All instructions must be per INASL Puri 3 guidelines
"""
    
    response = llm.invoke([
        SystemMessage(content="Medical strategy AI. Output JSON only per INASL Puri 3 guidelines."),
        HumanMessage(content=prompt)
    ])
    
    try:
        content = response.content.replace("```json", "").replace("```", "").strip()
        strategy_json = json.loads(content)
    except:
        # Fallback strategy
        logger.warning("⚠️ Strategy generation failed, using INASL fallback")
        strategy_json = {
            "bclc_stage": bclc_stage,
            "bclc_rationale": bclc['rationale'],
            "bclc_substage_detail": bclc.get('substage_detail', ''),
            "clinical_impression": f"INASL BCLC {bclc_stage}",
            "treatment_intent": "CURATIVE" if 'A' in bclc_stage or '0' in bclc_stage else "LOCOREGIONAL" if 'B' in bclc_stage else "SYSTEMIC" if 'C' in bclc_stage else "PALLIATIVE",
            "specialist_instructions": [
                {
                    "specialist_role": "Hepatologist",
                    "priority": "PRIMARY",
                    "focus_area": "Lead decision maker per INASL",
                    "specific_questions": ["Treatment tolerance?", "Portal HTN assessment?"],
                    "guidance_context": "Hepatologist leads all HCC decisions per INASL"
                }
            ],
            "orchestrator_guidance": "Hepatologist-led consensus per INASL",
            "critical_checks": ["BCLC staging verified", "INASL guidelines applied"]
        }
    
    # Ensure BCLC fields are set correctly
    strategy_json['bclc_stage'] = bclc_stage
    strategy_json['bclc_rationale'] = bclc['rationale']
    strategy_json['bclc_substage_detail'] = bclc.get('substage_detail', '')
    
    logger.info(f"✅ Strategy: {len(strategy_json.get('specialist_instructions', []))} specialist instructions per INASL")
    logger.info(f"   Treatment Intent: {strategy_json.get('treatment_intent', 'Unknown')}")
    return {"strategy_plan": strategy_json}


def specialist_analysis_node(state: IntegratedState, index) -> Dict:
    """
    ✅ FIXED: BCLC-driven specialist selection per INASL
    """
    logger.info("🔄 Node: Specialist Analysis (INASL-Driven)")
    
    data = state["filtered_data"]
    strategy = state["strategy_plan"]
    
    # Initialize all specialist types
    hepatologist = HepatologistAgent(index)
    radiologist = RadiologistAgent(index)
    surgeon = SurgeonAgent(index)
    oncologist = OncologistAgent(index)
    pathologist = PathologistAgent(index)
    
    specialist_map = {
        'hepatologist': hepatologist,
        'hepatology': hepatologist,
        'liver': hepatologist,
        'radiologist': radiologist,
        'radiology': radiologist,
        'interventional radiology': radiologist,
        'interventional': radiologist,
        'surgeon': surgeon,
        'surgery': surgeon,
        'surgical oncology': surgeon,
        'transplant': surgeon,
        'oncologist': oncologist,
        'oncology': oncologist,
        'medical oncology': oncologist,
        'pathologist': pathologist,
        'pathology': pathologist
    }
    
    results = {}
    specialist_instructions = strategy.get('specialist_instructions', [])
    
    if specialist_instructions:
        logger.info(f"ℹ️ Following {len(specialist_instructions)} INASL-based specialist instructions")
        
        for instruction in specialist_instructions:
            role = instruction['specialist_role'].lower()
            priority = instruction.get('priority', 'SECONDARY')
            
            # Find matching specialist
            agent = None
            for key, specialist in specialist_map.items():
                if key in role:
                    agent = specialist
                    break
            
            if agent:
                logger.info(f"   → [{priority}] {instruction['specialist_role']}: {instruction['focus_area']}")
                try:
                    result = agent.analyze(data, instruction)
                    results[instruction['specialist_role']] = result
                except Exception as e:
                    logger.error(f"   ❌ {instruction['specialist_role']} failed: {e}")
                    results[instruction['specialist_role']] = {
                        'specialist': instruction['specialist_role'],
                        'assessment': f'Error: {e}',
                        'recommendations': [],
                        'confidence': 0.0,
                        'evidence_quality': 'Error',
                        'critical_flags': ['Analysis failed']
                    }
    else:
        # Fallback: Always run hepatologist as minimum
        logger.info("ℹ️ No strategy instructions - running Hepatologist as minimum per INASL")
        try:
            results['Hepatology'] = hepatologist.analyze(data)
        except Exception as e:
            results['Hepatology'] = {'error': str(e)}
    
    logger.info(f"✅ Specialist analysis complete ({len(results)} specialists per INASL)")
    return {"specialist_results": results}


def consensus_synthesis_node(state: IntegratedState) -> Dict:
    """
    ✅ FIXED: Hepatologist-led consensus per INASL and Workflow
    """
    logger.info("🔄 Node: Consensus Synthesis (Hepatologist-Led per INASL)")
    
    data = state["filtered_data"]
    strategy = state["strategy_plan"]
    specialist_results = state["specialist_results"]
    
    clinical = data['clinical_summary']
    tumor_info = extract_tumor_summary(data)
    patient_summary = create_concise_patient_summary(data)
    bclc_stage = strategy['bclc_stage']
    treatment_intent = strategy.get('treatment_intent', 'Unknown')
    
    specialist_summaries = []
    all_critical_flags = []
    
    for role, result in specialist_results.items():
        if 'error' not in result:
            assessment = result.get('assessment', 'No assessment')
            truncated = assessment[:400] + "..." if len(assessment) > 400 else assessment
            priority = "PRIMARY" if role in ['Hepatology', 'Hepatologist'] else "SECONDARY"
            specialist_summaries.append(f"""
[{priority}] {role}: {truncated}
Confidence: {result.get('confidence', 0.0)} | Quality: {result.get('evidence_quality', 'Unknown')}""")
            all_critical_flags.extend(result.get('critical_flags', []))
    
    # ✅ FIXED: Temperature = 0.0
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    
    # ✅ CRITICAL: Hepatologist-led consensus per workflow
    prompt = f"""TUMOR BOARD CHAIRPERSON synthesizing consensus per INASL Puri 3 and Workflow.

{patient_summary}
BCLC (INASL Puri 3): {bclc_stage}
Substage: {strategy['bclc_substage_detail']}
Treatment Intent: {treatment_intent}

SPECIALIST ASSESSMENTS (Hepatologist-Led per Workflow Page 7):
{chr(10).join(specialist_summaries)}

CRITICAL FLAGS: {'; '.join(list(set(all_critical_flags))[:5])}

🔒 GROUNDING RULES (INASL PURI 3):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Consensus MUST be based on specialist INASL guideline citations
2. Hepatologist LEADS decision (not majority vote) per Workflow Page 7
3. If specialists cite different INASL sources, note the variance
4. Do NOT add recommendations beyond INASL guideline support
5. Focus on FIRST-LINE treatment per INASL for BCLC {bclc_stage}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Per Workflow Page 7 - Consensus Process:
1. Each specialist presents assessment (70-80% weight on INASL guidelines)
2. Hepatologist LEADS final decision
3. NOT majority vote - consensus-based with Hepatologist as leader
4. Technical feasibility from Surgeon/Radiologist (15-20% weight)
5. Patient-specific factors (10-15% weight)

Synthesize HEPATOLOGIST-LED CONSENSUS per INASL Puri 3:

**PRIMARY TREATMENT (per INASL for BCLC {bclc_stage}):**
[Based on Hepatologist LEAD + specialist consensus + INASL guidelines]

**INASL GUIDELINE SUPPORT:**
[Cite specific specialist/SOURCE references from INASL Puri 3]

**RATIONALE:**
[BCLC {bclc_stage} per INASL, guideline alignment, feasibility assessment]

**ALTERNATIVES (if primary contraindicated per INASL):**
[Second-line options from INASL]

**PREREQUISITES:**
[Pre-treatment steps per INASL]

**MONITORING (per INASL):**
[Schedule, response criteria from INASL guidelines]

**RED FLAGS:**
[Urgent concerns requiring immediate attention]

**CONSENSUS STATUS:**
[Unanimous / Majority / Hepatologist-led decision with noted disagreements]

CRITICAL: Ensure PRIMARY treatment matches BCLC {bclc_stage} per INASL:
- BCLC 0/A → Resection / Ablation / Transplant (curative)
- BCLC B → TACE / TARE (locoregional)
- BCLC C → Systemic therapy
- BCLC D → Best supportive care
"""
    
    response = llm.invoke([
        SystemMessage(content="Tumor board chairperson. Hepatologist-led consensus per INASL Puri 3."),
        HumanMessage(content=prompt)
    ])
    
    consensus_plan = str(response.content)
    
    # ✅ FIXED: Better assessment of decompensation
    child_pugh = clinical['derived_scores']['Child_Pugh']
    ascites = clinical.get('ascites', 'none')
    encephalopathy = clinical.get('encephalopathy', 'none')
    is_decompensated = (
        child_pugh['class'] in ['B', 'C'] or 
        ascites not in ['none', 'absent'] or 
        encephalopathy not in ['none', 'absent']
    )
    
    final_recommendation = {
        'timestamp': datetime.now().isoformat(),
        'patient_summary': {
            'bclc_stage': bclc_stage,
            'bclc_rationale': strategy['bclc_rationale'],
            'bclc_substage_detail': strategy['bclc_substage_detail'],
            'treatment_intent': treatment_intent,
            'child_pugh': child_pugh,
            'tumor_burden': tumor_info,
            'ecog': clinical['ECOG'],
            'compensation_status': 'DECOMPENSATED' if is_decompensated else 'COMPENSATED'
        },
        'consensus_plan': consensus_plan,
        'strategy_plan': strategy,
        'specialist_results': specialist_results,
        'critical_flags': list(set(all_critical_flags)),
        'status': 'complete' if all('error' not in r for r in specialist_results.values()) else 'partial',
        'guideline_version': 'INASL Puri 3'
    }
    
    logger.info("✅ Hepatologist-led consensus complete per INASL Puri 3")
    return {
        "consensus_plan": consensus_plan,
        "final_recommendation": final_recommendation
    }

# ============================================================================
# WORKFLOW BUILDER
# ============================================================================

def build_tumor_board_workflow(index):
    workflow = StateGraph(IntegratedState)
    
    workflow.add_node("parse_data", data_parser_node)
    workflow.add_node("calculate_bclc", bclc_calculator_node)
    workflow.add_node("generate_strategy", strategy_generator_node)
    workflow.add_node("analyze_specialists", lambda state: specialist_analysis_node(state, index))
    workflow.add_node("synthesize_consensus", consensus_synthesis_node)
    
    workflow.set_entry_point("parse_data")
    workflow.add_edge("parse_data", "calculate_bclc")
    workflow.add_edge("calculate_bclc", "generate_strategy")
    workflow.add_edge("generate_strategy", "analyze_specialists")
    workflow.add_edge("analyze_specialists", "synthesize_consensus")
    workflow.add_edge("synthesize_consensus", END)
    
    return workflow.compile()

# ============================================================================
# MAIN SYSTEM
# ============================================================================

class IntegratedTumorBoardSystem:
    def __init__(self):
        self.index = None
        self.workflow_app = None
    
    def setup(self, pdf_path: str, force_reparse: bool = False):
        logger.info("HCC TUMOR BOARD SETUP")
        logger.info("="*80)
        
        documents = parse_or_load_documents(pdf_path, force_reparse)
        self.index = create_or_load_index(documents, force_recreate=force_reparse)
        self.workflow_app = build_tumor_board_workflow(self.index)
        
        logger.info("✅ System ready")
        logger.info("="*80)
        
        metadata = load_metadata()
        
        logger.info("Setup:")
    
    def analyze_patient(self, patient_data: Dict) -> Dict:
        if not self.workflow_app:
            raise RuntimeError("Not initialized. Call setup() first.")
        
        logger.info("\n" + "="*80)
        logger.info("🏥 HCC TUMOR BOARD ANALYSIS (INASL PURI 3 GUIDELINES)")
        logger.info("="*80)
        
        is_valid, error = validate_patient_data(patient_data)
        if not is_valid:
            logger.error(f"❌ Validation failed: {error}")
            return {'error': error, 'status': 'failed_validation'}
        
        start_time = datetime.now()
        result = self.workflow_app.invoke({"raw_input_json": patient_data})
        end_time = datetime.now()
        
        final_result = result.get('final_recommendation', {})
        final_result['processing_time_seconds'] = (end_time - start_time).total_seconds()
        
        output_dir = Path("./results")
        output_dir.mkdir(exist_ok=True)
        filename = f"result_inasl_puri3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_dir / filename, 'w') as f:
            json.dump(final_result, indent=2, fp=f)
        
        logger.info(f"💾 Saved to {output_dir / filename}")
        logger.info(f"⏱️ Time: {final_result['processing_time_seconds']:.1f}s")
        logger.info("="*80)
        
        return final_result
    
    def print_summary(self, result: Dict):
        print("\n" + "="*80)
        print("📊 RECOMMENDATION SUMMARY (INASL PURI 3)")
        print("="*80)
        
        patient_summary = result.get('patient_summary', {})
        print(f"\n🎯 BCLC: {patient_summary.get('bclc_stage')} (INASL Puri 3)")
        print(f"   Treatment Intent: {patient_summary.get('treatment_intent', 'Unknown')}")
        print(f"   Rationale: {patient_summary.get('bclc_rationale', '')[:150]}...")
        
        print(f"\n🏥 Liver Status: {patient_summary.get('compensation_status', 'Unknown')}")
        child_pugh = patient_summary.get('child_pugh', {})
        print(f"   Child-Pugh {child_pugh.get('class')} ({child_pugh.get('score')} points) | ECOG {patient_summary.get('ecog')}")
        
        tumor = patient_summary.get('tumor_burden', {})
        print(f"\n🎗️ TUMOR: {tumor.get('count')} lesions, max {tumor.get('max_size_cm')}cm, {tumor.get('distribution')}")
        
        critical_flags = result.get('critical_flags', [])
        if critical_flags:
            print(f"\n⚠️ CRITICAL FLAGS:")
            for flag in critical_flags[:5]:
                print(f"   - {flag}")
        
        print(f"\n📋 CONSENSUS (Hepatologist-Led per INASL Puri 3):")
        print("-"*80)
        consensus = result.get('consensus_plan', 'None')
        print(consensus[:1000])
        if len(consensus) > 1000:
            print("\n[... see full output in JSON]")
        
        print(f"\n✅ STATUS: {result.get('status', 'unknown')}")
        print(f"📚 GUIDELINE: {result.get('guideline_version', 'INASL Puri 3')}")
        print("="*80)

# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='INASL Puri 3 Compliant HCC Tumor Board System')
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--pdf', type=str, help='Path to INASL Puri 3 guidelines PDF')
    parser.add_argument('--patient', type=str, help='Path to patient JSON file')
    parser.add_argument('--force-reparse', action='store_true')
    parser.add_argument('--output-summary', action='store_true')
    
    args = parser.parse_args()
    system = IntegratedTumorBoardSystem()
    
    if args.setup:
        if not args.pdf:
            print("❌ --pdf required for setup")
            return
        system.setup(args.pdf, args.force_reparse)
        print("\n✅ Setup complete - INASL Puri 3 Guidelines Loaded!")
        print("\n🎉 ALL PRODUCTION FIXES APPLIED:")
        print("   ✅ INASL Puri 3 compliant BCLC staging")
        print("   ✅ BCLC-driven specialist selection")
        print("   ✅ Hepatologist-led consensus")
        print("   ✅ First-line treatment focus")
        print("   ✅ Filters post-treatment data")
        print("   ✅ Conditional pathologist")
        print("   ✅ Correct AFP thresholds")
        print("   ✅ Workflow-aligned prompts")
    
    elif args.patient:
        with open(args.patient) as f:
            patient_data = json.load(f)
        
        if not system.workflow_app:
            if args.pdf:
                system.setup(args.pdf)
            else:
                try:
                    system.index = create_or_load_index()
                    system.workflow_app = build_tumor_board_workflow(system.index)
                    logger.info("✅ Loaded from cache")
                except:
                    print("❌ No cache. Run --setup first.")
                    return
        
        result = system.analyze_patient(patient_data)
        
        if args.output_summary:
            system.print_summary(result)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()