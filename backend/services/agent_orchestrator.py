"""
Agent Orchestrator Service
Sequential processing:
1. Processes three agents (radiology, clinical, pathology)
2. Formats output similar to sampleOUTPUTpatient.json
3. Feeds output to HCC tumor board system
4. Processes tumor board summary agent
5. Returns all outputs in structured format
"""

from typing import Dict, Any, Optional
from openai import OpenAI, RateLimitError, APIError
import os
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Add backend directory to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from radiology_agent import RadiologyAgent, OpenAILLM
from clinical_agent import ClinicalDataAgent
from pathology_agent import PathologyMolecularAgent
from tumor_board_summary_agent import TumorBoardNotesAgent

# Import tumor board system
# hcc_tumour_board is in the parent directory (backend/)
# Since we already added backend_dir to sys.path, we can import directly
TUMOR_BOARD_AVAILABLE = False
IntegratedTumorBoardSystem = None
create_or_load_index = None
build_tumor_board_workflow = None

try:
    # Try importing the module
    import hcc_tumour_board
    
    # Try to get the required classes/functions
    try:
        IntegratedTumorBoardSystem = hcc_tumour_board.IntegratedTumorBoardSystem
        create_or_load_index = hcc_tumour_board.create_or_load_index
        build_tumor_board_workflow = hcc_tumour_board.build_tumor_board_workflow
        TUMOR_BOARD_AVAILABLE = True
        logger.info("✅ HCC tumor board system module loaded successfully")
    except AttributeError as e:
        logger.warning(f"HCC tumor board system module loaded but missing required components: {e}")
        TUMOR_BOARD_AVAILABLE = False
except ImportError as e:
    error_msg = str(e)
    if "No module named" in error_msg:
        # Check if it's a dependency issue
        if "llama" in error_msg.lower() or "langgraph" in error_msg.lower() or "langchain" in error_msg.lower():
            logger.warning(f"HCC tumor board system dependencies not installed: {e}")
            logger.info("   Install required packages: pip install langgraph langchain llama-index llama-parse")
        else:
            logger.warning(f"HCC tumor board system module not found: {e}")
    else:
        logger.warning(f"HCC tumor board system import error: {e}")
    TUMOR_BOARD_AVAILABLE = False
except Exception as e:
    logger.warning(f"Unexpected error loading HCC tumor board system: {type(e).__name__}: {e}")
    import traceback
    logger.debug(f"Traceback: {traceback.format_exc()}")
    TUMOR_BOARD_AVAILABLE = False


class AgentOrchestrator:
    """
    Sequential orchestrator:
    1. Processes radiology, clinical, pathology agents
    2. Formats output in sampleOUTPUTpatient.json format
    3. Feeds to HCC tumor board system
    4. Processes tumor board summary
    5. Returns structured output
    """

    def __init__(self, openai_api_key: Optional[str] = None, tumor_board_pdf_path: Optional[str] = None):
        """
        Initialize all agents with shared OpenAI client.
        
        Args:
            openai_api_key: OpenAI API key
            tumor_board_pdf_path: Optional path to INASL PDF for tumor board system
        """
        self.api_key = openai_api_key
        
        # Initialize OpenAI client
        if self.api_key:
            api_key_value = self.api_key
        else:
            # Try to load from dotenv if available
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass  # dotenv not available, will use environment variable directly
            api_key_value = os.getenv("OPENAI_API_KEY")
            if not api_key_value:
                raise ValueError("OPENAI_API_KEY must be provided or set in environment")
        
        self.client = OpenAI(api_key=api_key_value)
        
        # Initialize three agents (radiology, clinical, pathology)
        self.radiology_llm = OpenAILLM(api_key=api_key_value)
        self.radiology_agent = RadiologyAgent(llm=self.radiology_llm)
        self.clinical_agent = ClinicalDataAgent(openai_api_key=api_key_value)
        self.pathology_agent = PathologyMolecularAgent(openai_api_key=api_key_value)
        self.tumor_board_summary_agent = TumorBoardNotesAgent()
        
        # Initialize tumor board system (optional)
        self.tumor_board_system = None
        
        # Auto-detect PDF path: check env var, parameter, or common locations
        self.tumor_board_pdf_path = tumor_board_pdf_path or os.getenv("INASL_PDF_PATH")
        
        # If not provided, try to auto-detect in backend directory
        if not self.tumor_board_pdf_path:
            backend_pdf_paths = [
                os.path.join(backend_dir, "HCC_guideline_INSASL.pdf"),  # Actual filename
                os.path.join(backend_dir, "HCC_guideline_INASL.pdf"),  # Alternative spelling
                os.path.join(backend_dir, "INASL_Puri_3.pdf"),
                os.path.join(backend_dir, "INASL.pdf"),
            ]
            
            for pdf_path in backend_pdf_paths:
                if os.path.exists(pdf_path):
                    self.tumor_board_pdf_path = pdf_path
                    logger.info(f"✅ Auto-detected PDF: {pdf_path}")
                    break
        
        # Try to load from cache first (faster)
        if TUMOR_BOARD_AVAILABLE and create_or_load_index is not None and build_tumor_board_workflow is not None and IntegratedTumorBoardSystem is not None:
            try:
                # Check if cache directory exists (relative to backend directory)
                cache_dir = Path(backend_dir) / "cache"
                index_dir = cache_dir / "vector_index_large"
                
                # Change to backend directory temporarily for cache loading
                # (since hcc_tumour_board.py uses relative paths)
                original_cwd = os.getcwd()
                try:
                    os.chdir(backend_dir)
                    
                    if index_dir.exists():
                        try:
                            index = create_or_load_index()
                            if index:
                                self.tumor_board_system = IntegratedTumorBoardSystem()
                                self.tumor_board_system.index = index
                                self.tumor_board_system.workflow_app = build_tumor_board_workflow(index)
                                logger.info("✅ Loaded tumor board system from cache")
                            else:
                                logger.info("ℹ️ Cached index exists but could not be loaded")
                        except Exception as e:
                            logger.warning(f"Could not load from cache: {e}, will try PDF initialization")
                            # Fall through to PDF initialization
                    
                    # If cache didn't work but we have PDF, initialize from PDF
                    if not self.tumor_board_system and self.tumor_board_pdf_path:
                        try:
                            self._initialize_tumor_board_system()
                        except Exception as e:
                            logger.warning(f"Could not initialize tumor board system from PDF: {e}")
                            self.tumor_board_system = None
                    elif not self.tumor_board_system and not index_dir.exists():
                        logger.info("ℹ️ No cache or PDF found - tumor board system will be unavailable")
                finally:
                    os.chdir(original_cwd)
                    
            except Exception as e:
                logger.warning(f"Error checking cache/initializing tumor board system: {e}")
                self.tumor_board_system = None
        elif TUMOR_BOARD_AVAILABLE and self.tumor_board_pdf_path:
            # If cache functions not available but PDF is provided, try direct initialization
            try:
                self._initialize_tumor_board_system()
            except Exception as e:
                logger.warning(f"Could not initialize tumor board system: {e}")
                self.tumor_board_system = None
    
    def _initialize_tumor_board_system(self):
        """Initialize the HCC tumor board system with PDF."""
        if not TUMOR_BOARD_AVAILABLE or IntegratedTumorBoardSystem is None:
            logger.warning("Tumor board system not available for initialization")
            return
        
        if not self.tumor_board_pdf_path:
            logger.warning("No PDF path provided for tumor board system")
            return
        
        # Handle both absolute and relative paths
        pdf_path = Path(self.tumor_board_pdf_path)
        if not pdf_path.is_absolute():
            # Try relative to backend directory
            pdf_path = Path(backend_dir) / self.tumor_board_pdf_path
        
        # If still not found, try as absolute path
        if not pdf_path.exists():
            pdf_path = Path(self.tumor_board_pdf_path)
        
        if not pdf_path.exists():
            logger.warning(f"INASL PDF not found at {self.tumor_board_pdf_path} (checked: {pdf_path})")
            return
        
        try:
            self.tumor_board_system = IntegratedTumorBoardSystem()
            # Use absolute path for setup
            abs_pdf_path = str(pdf_path.resolve())
            
            # Change to backend directory for setup (since hcc_tumour_board.py uses relative paths)
            original_cwd = os.getcwd()
            try:
                os.chdir(backend_dir)
                # Convert absolute path to relative path from backend directory
                rel_pdf_path = os.path.relpath(abs_pdf_path, backend_dir)
                self.tumor_board_system.setup(rel_pdf_path, force_reparse=False)
                logger.info(f"✅ Tumor board system initialized from PDF: {abs_pdf_path}")
            finally:
                os.chdir(original_cwd)
        except Exception as e:
            logger.error(f"Failed to initialize tumor board system: {e}")
            self.tumor_board_system = None

    
    #Initializing the processing pipeline
    def process_agents(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process three agents (Step 1) and format output (Step 2).
        This is the preview stage where output can be reviewed and edited before tumor board processing.
        
        Args:
            patient_data: Full patient data including demographics, clinical, lab_data,
                         radiology, pathology, treatment_history, tumor_board
        
        Returns:
            Formatted output in sampleOUTPUTpatient.json format, ready for review
        """
        errors = {}
        
        # Helper to handle errors with better messages
        def handle_agent_error(agent_name: str, error: Exception) -> str:
            """Format error messages for better user experience."""
            error_str = str(error)
            if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                return f"OpenAI API rate limit/quota exceeded. Please check your API plan and billing."
            elif "insufficient_quota" in error_str:
                return f"OpenAI API quota exceeded. Please check your billing details."
            else:
                return f"{agent_name} processing failed: {error_str[:200]}"

        # ============================================================
        # STEP 1: Process three agents (Radiology, Clinical, Pathology)
        # ============================================================
        logger.info("Step 1: Processing three agents (Radiology, Clinical, Pathology)")
        
        radiology_result = None
        clinical_result = None
        pathology_result = None

        # 1.1 Process Radiology
        try:
            radiology_section = patient_data.get("radiology", {})
            if radiology_section and radiology_section.get("studies"):
                radiology_result = self.radiology_agent.process(radiology_section)
                time.sleep(0.5)  # Small delay to avoid rate limits
                logger.info("✅ Radiology agent completed")
            else:
                logger.warning("⚠️ No radiology data found")
        except Exception as e:
            error_msg = handle_agent_error("Radiology", e)
            errors["radiology"] = error_msg
            logger.error(f"❌ Radiology agent error: {e}")

        # 1.2 Process Clinical
        try:
            clinical_input = {
                "demographics": patient_data.get("demographics", {}),
                "clinical": patient_data.get("clinical", {}),
                "lab_data": patient_data.get("lab_data", {}),
                "ground_truth": patient_data.get("ground_truth")  # Pass through ground truth
            }
            clinical_result = self.clinical_agent.process(clinical_input)
            time.sleep(0.5)  # Small delay to avoid rate limits
            logger.info("✅ Clinical agent completed")
        except Exception as e:
            error_msg = handle_agent_error("Clinical", e)
            errors["clinical"] = error_msg
            logger.error(f"❌ Clinical agent error: {e}")

        # 1.3 Process Pathology
        try:
            pathology_input = {"pathology": patient_data.get("pathology", {})}
            pathology_result = self.pathology_agent.process(pathology_input)
            time.sleep(0.5)  # Small delay to avoid rate limits
            logger.info("✅ Pathology agent completed")
        except Exception as e:
            error_msg = handle_agent_error("Pathology", e)
            errors["pathology"] = error_msg
            logger.error(f"❌ Pathology agent error: {e}")

        # ============================================================
        # STEP 2: Format output similar to sampleOUTPUTpatient.json
        # ============================================================
        logger.info("Step 2: Formatting agent outputs")
        
        # Build structured output matching sampleOUTPUTpatient.json format
        agent_output = {}
        
        if clinical_result:
            agent_output["clinical_summary"] = clinical_result.get("clinical_summary", {})
            agent_output["agent_metadata"] = {
                "clinical_agent_confidence": clinical_result.get("agent_metadata", {}).get("clinical_agent_confidence")
            }
            agent_output["ground_truth"] = clinical_result.get("ground_truth", {
                "clinical_scores": {
                    "Child_Pugh": {"score": None, "class": None},
                    "MELD": None,
                    "MELD_Na": None,
                    "ALBI": {"score": None, "grade": None}
                }
            })
        
        if radiology_result:
            agent_output["radiology_summary"] = radiology_result.get("radiology_summary", {})
            if "agent_metadata" in agent_output:
                agent_output["agent_metadata"]["radiology_agent_confidence"] = (
                    radiology_result.get("radiology_summary", {})
                    .get("agent_metadata", {})
                    .get("radiology_agent_confidence")
                )
        
        if pathology_result:
            agent_output["pathology_summary"] = pathology_result.get("pathology_summary", {})
            if "agent_metadata" in agent_output:
                agent_output["agent_metadata"]["pathology_agent_confidence"] = (
                    pathology_result.get("pathology_summary", {})
                    .get("agent_metadata", {})
                    .get("pathology_agent_confidence")
                )
        
        # Add individual agent responses for frontend display
        agent_output["individual_agent_responses"] = {
            "radiology": radiology_result,
            "clinical": clinical_result,
            "pathology": pathology_result
        }
        
        # Add errors if any
        if errors:
            agent_output["errors"] = errors
        
        logger.info("✅ Agent processing and formatting completed - ready for review")
        return agent_output
    
    def process_tumor_board(
        self, 
        agent_output: Dict[str, Any], 
        patient_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process tumor board system (Step 3) and tumor board summary (Step 4).
        This is called after user review and approval of agent outputs.
        
        Args:
            agent_output: Formatted output from process_agents() (may have been edited by user)
            patient_data: Original patient data (needed for tumor board summary)
        
        Returns:
            Complete output including tumor board results and summary
        """
        errors = {}
        
        # Helper to handle errors with better messages
        def handle_agent_error(agent_name: str, error: Exception) -> str:
            """Format error messages for better user experience."""
            error_str = str(error)
            if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                return f"OpenAI API rate limit/quota exceeded. Please check your API plan and billing."
            elif "insufficient_quota" in error_str:
                return f"OpenAI API quota exceeded. Please check your billing details."
            else:
                return f"{agent_name} processing failed: {error_str[:200]}"
        
        # Extract individual agent results from agent_output
        individual_responses = agent_output.get("individual_agent_responses", {})
        radiology_result = individual_responses.get("radiology")
        clinical_result = individual_responses.get("clinical")
        pathology_result = individual_responses.get("pathology")

        # ============================================================
        # STEP 3: Feed to HCC Tumor Board System
        # ============================================================
        tumor_board_result = None
        if self.tumor_board_system and self.tumor_board_system.workflow_app:
            logger.info("Step 3: Processing through HCC tumor board system")
            try:
                # Prepare input for tumor board (needs clinical_summary, radiology_summary, pathology_summary)
                tumor_board_input = {
                    "clinical_summary": agent_output.get("clinical_summary", {}),
                    "radiology_summary": agent_output.get("radiology_summary", {}),
                    "pathology_summary": agent_output.get("pathology_summary", {})
                }
                
                # Check if we have minimum required data
                has_clinical = bool(tumor_board_input["clinical_summary"])
                has_radiology = bool(tumor_board_input["radiology_summary"])
                
                if has_clinical and has_radiology:
                    tumor_board_result = self.tumor_board_system.analyze_patient(tumor_board_input)
                    logger.info("✅ Tumor board system completed")
                else:
                    logger.warning("⚠️ Insufficient data for tumor board system (requires clinical and radiology)")
                    errors["tumor_board"] = "Insufficient data: requires clinical_summary and radiology_summary"
            except Exception as e:
                error_msg = handle_agent_error("Tumor Board System", e)
                errors["tumor_board"] = error_msg
                logger.error(f"❌ Tumor board system error: {e}")
        else:
            if TUMOR_BOARD_AVAILABLE:
                logger.info("ℹ️ Tumor board system not initialized. Configure INASL_PDF_PATH environment variable or provide PDF path to enable.")
                # Don't add to errors - this is expected if PDF not configured
            else:
                logger.info("ℹ️ Tumor board system module not available")
                # Don't add to errors - this is a configuration issue, not a failure

        # ============================================================
        # STEP 4: Process Tumor Board Summary Agent
        # ============================================================
        logger.info("Step 4: Processing tumor board summary agent")
        
        tumor_board_summary_result = None
        try:
            # Prepare tumor board data from patient input
            tumor_board_data = patient_data.get("tumor_board", {})
            treatment_history_data = patient_data.get("treatment_history", {})
            
            # If we have tumor board result, we can use it to enrich the summary
            # But the summary agent primarily uses the input tumor_board and treatment_history
            if tumor_board_data or treatment_history_data:
                tumor_board_summary_result = self.tumor_board_summary_agent.run(
                    tumor_board_data,
                    treatment_history_data
                )
                time.sleep(0.5)  # Small delay to avoid rate limits
                logger.info("✅ Tumor board summary agent completed")
            else:
                logger.warning("⚠️ No tumor board or treatment history data for summary agent")
        except Exception as e:
            error_msg = handle_agent_error("Tumor Board Summary", e)
            errors["tumor_board_summary"] = error_msg
            logger.error(f"❌ Tumor board summary agent error: {e}")
        
        # Combine errors from agent_output if any
        if agent_output.get("errors"):
            errors.update(agent_output["errors"])
        
        # Build final output similar to process_all
        final_output = self._compile_final_output(
            agent_output,
            radiology_result,
            clinical_result,
            pathology_result,
            tumor_board_result,
            tumor_board_summary_result,
            errors
        )
        
        logger.info("✅ Tumor board processing completed")
        return final_output
    
    def process_all(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sequential processing pipeline (backward compatible):
        1. Process three agents (radiology, clinical, pathology)
        2. Format output in sampleOUTPUTpatient.json format
        3. Feed to HCC tumor board system
        4. Process tumor board summary agent
        5. Return all outputs
        
        This method calls process_agents() and process_tumor_board() sequentially.
        For human-in-the-loop workflow, use process_agents() and process_tumor_board() separately.
        
        Args:
            patient_data: Full patient data including demographics, clinical, lab_data,
                         radiology, pathology, treatment_history, tumor_board
        
        Returns:
            Structured output with all stages of processing
        """
        # Step 1-2: Process agents and format output
        agent_output = self.process_agents(patient_data)
        
        # Step 3-4: Process tumor board system and summary
        final_output = self.process_tumor_board(agent_output, patient_data)
        
        return final_output
    
    def _compile_final_output(
        self,
        agent_output: Dict[str, Any],
        radiology_result: Optional[Dict[str, Any]],
        clinical_result: Optional[Dict[str, Any]],
        pathology_result: Optional[Dict[str, Any]],
        tumor_board_result: Optional[Dict[str, Any]],
        tumor_board_summary_result: Optional[Dict[str, Any]],
        errors: Dict[str, str]
    ) -> Dict[str, Any]:

        # ============================================================
        # STEP 5: Compile final output (Backward compatible + new structure)
        # ============================================================
        logger.info("Step 5: Compiling final output")
        
        # Add tumor board summary to agent_output if available
        if tumor_board_summary_result:
            agent_output["notes_summary"] = tumor_board_summary_result.get("notes_summary", {})

        # Build backward-compatible structure for frontend
        # Frontend expects: agent_responses, culminated_plan_of_action, agent_metadata
        backward_compatible = {
            # Individual agent responses (for frontend display)
            "agent_responses": {
                "radiology": radiology_result,
                "clinical": clinical_result,
                "pathology": pathology_result,
                "tumor_board": tumor_board_summary_result  # Use summary agent output for tumor_board
            },
            
            # Agent metadata with confidence scores
            "agent_metadata": {
                "errors": errors if errors else None,
                "radiology_confidence": (
                    radiology_result.get("radiology_summary", {})
                    .get("agent_metadata", {})
                    .get("radiology_agent_confidence")
                    if radiology_result else None
                ),
                "clinical_confidence": (
                    clinical_result.get("agent_metadata", {})
                    .get("clinical_agent_confidence")
                    if clinical_result else None
                ),
                "pathology_confidence": (
                    pathology_result.get("pathology_summary", {})
                    .get("agent_metadata", {})
                    .get("pathology_agent_confidence")
                    if pathology_result else None
                ),
            },
            
            # Generate culminated plan from tumor board output if available
            "culminated_plan_of_action": None
        }
        
        # Generate culminated plan from tumor board system output
        if tumor_board_result:
            try:
                culminated_plan = self._generate_culminated_plan_from_tumor_board(
                    radiology_result, 
                    clinical_result, 
                    pathology_result, 
                    tumor_board_result
                )
                backward_compatible["culminated_plan_of_action"] = culminated_plan
            except Exception as e:
                logger.warning(f"Failed to generate culminated plan: {e}")
                # Fallback plan
                backward_compatible["culminated_plan_of_action"] = {
                    "summary": "Comprehensive analysis completed. Review individual agent responses and tumor board recommendations.",
                    "recommendations": [],
                    "key_findings": []
                }
        elif all([radiology_result, clinical_result, pathology_result]):
            # Fallback: generate plan from three agents if tumor board not available
            try:
                culminated_plan = self._generate_culminated_plan_from_agents(
                    radiology_result, 
                    clinical_result, 
                    pathology_result
                )
                backward_compatible["culminated_plan_of_action"] = culminated_plan
            except Exception as e:
                logger.warning(f"Failed to generate culminated plan from agents: {e}")
                backward_compatible["culminated_plan_of_action"] = {
                    "summary": "Comprehensive analysis completed. Review individual agent responses for detailed findings.",
                    "recommendations": ["Review all agent outputs for comprehensive assessment"],
                    "key_findings": []
                }

        # Build comprehensive final response with both old and new structures
        final_output = {
            # Backward compatible structure (for frontend)
            **backward_compatible,
            
            # NEW: Structured outputs for detailed access
            "structured_outputs": {
                # Stage 1: Three agent outputs (formatted like sampleOUTPUTpatient.json)
                "agent_outputs": agent_output,
                
                # Stage 2: Tumor board system output
                "tumor_board_output": tumor_board_result,
                
                # Stage 3: Tumor board summary output
                "tumor_board_summary_output": tumor_board_summary_result,
            },
            
            # NEW: Processing metadata
            "processing_metadata": {
                "errors": errors if errors else None,
                "tumor_board_system_available": self.tumor_board_system is not None and self.tumor_board_system.workflow_app is not None,
                "stages_completed": {
                    "three_agents": all([radiology_result, clinical_result, pathology_result]),
                    "tumor_board_system": tumor_board_result is not None,
                    "tumor_board_summary": tumor_board_summary_result is not None
                }
            }
        }
        
        logger.info("✅ Sequential processing pipeline completed")
        return final_output
    
    def _generate_culminated_plan_from_tumor_board(self, radiology_result, clinical_result, pathology_result, tumor_board_result):
        """Generate culminated plan from tumor board system output."""
        # Extract key information from tumor board result
        consensus_plan = tumor_board_result.get("consensus_plan", "")
        final_recommendation = tumor_board_result.get("final_recommendation", {})
        patient_summary = final_recommendation.get("patient_summary", {})
        bclc_stage = patient_summary.get("bclc_stage", "Unknown")
        treatment_intent = patient_summary.get("treatment_intent", "Unknown")
        
        # Extract recommendations from consensus plan
        recommendations = []
        key_findings = []
        
        if consensus_plan:
            # Try to extract structured information from consensus plan
            lines = consensus_plan.split('\n')
            current_section = None
            
            for line in lines:
                line_stripped = line.strip()
                if '**PRIMARY TREATMENT**' in line_stripped or 'PRIMARY TREATMENT' in line_stripped:
                    current_section = "treatment"
                elif '**RECOMMENDATION**' in line_stripped or 'RECOMMENDATION' in line_stripped:
                    current_section = "recommendation"
                elif '**KEY FINDINGS**' in line_stripped or 'KEY FINDINGS' in line_stripped:
                    current_section = "findings"
                elif line_stripped and not line_stripped.startswith('*') and current_section:
                    if current_section == "recommendation" and len(recommendations) < 5:
                        recommendations.append(line_stripped)
                    elif current_section == "findings" and len(key_findings) < 5:
                        key_findings.append(line_stripped)
        
        # Build summary
        summary = f"BCLC Stage {bclc_stage} - {treatment_intent} intent. "
        if consensus_plan:
            summary += consensus_plan[:300] + ("..." if len(consensus_plan) > 300 else "")
        else:
            summary += "Multidisciplinary tumor board analysis completed."
        
        return {
            "summary": summary,
            "recommendations": recommendations if recommendations else [
                f"BCLC Stage {bclc_stage} treatment approach",
                f"Treatment intent: {treatment_intent}",
                "Review full tumor board consensus for detailed recommendations"
            ],
            "key_findings": key_findings if key_findings else [
                f"BCLC Stage: {bclc_stage}",
                f"Treatment Intent: {treatment_intent}"
            ]
        }
    
    def _generate_culminated_plan_from_agents(self, radiology_result, clinical_result, pathology_result):
        """Generate culminated plan from three agent outputs when tumor board is not available."""
        findings = []
        
        if radiology_result:
            rad_summary = radiology_result.get("radiology_summary", {})
            if rad_summary.get("radiology_interpretation"):
                findings.append(f"Radiology: {rad_summary['radiology_interpretation'][:200]}")
        
        if clinical_result:
            clinical_summary = clinical_result.get("clinical_summary", {})
            if clinical_summary.get("clinical_interpretation"):
                findings.append(f"Clinical: {clinical_summary['clinical_interpretation'][:200]}")
            # Add key scores
            derived = clinical_summary.get("derived_scores", {})
            cp = derived.get("Child_Pugh", {})
            if cp.get("class"):
                findings.append(f"Child-Pugh: {cp['class']} (score: {cp.get('score', 'N/A')})")
            if derived.get("MELD_Na"):
                findings.append(f"MELD-Na: {derived['MELD_Na']}")
        
        if pathology_result:
            path_summary = pathology_result.get("pathology_summary", {})
            if path_summary.get("pathology_interpretation"):
                findings.append(f"Pathology: {path_summary['pathology_interpretation'][:200]}")
        
        if not findings:
            return {
                "summary": "Agent analysis completed. Review individual agent outputs for detailed findings.",
                "recommendations": ["Review all agent outputs for comprehensive assessment"],
                "key_findings": []
            }
        
        # Use LLM to synthesize plan
        prompt = f"""You are a hepatology tumor board coordinator synthesizing findings from multiple specialists.

FINDINGS FROM AGENTS:
{chr(10).join(f"- {f}" for f in findings)}

TASK:
Generate a concise, actionable plan of action (3-5 sentences) that synthesizes these findings.
Focus on:
1. Key clinical decisions
2. Treatment recommendations
3. Follow-up actions
4. Critical considerations

Return JSON with:
{{
  "summary": "2-3 sentence executive summary",
  "recommendations": ["action item 1", "action item 2", ...],
  "key_findings": ["finding 1", "finding 2", ...]
}}
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a hepatology tumor board coordinator. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=500
            )
            
            import json
            plan = json.loads(response.choices[0].message.content)
            return plan
        except (RateLimitError, APIError) as e:
            logger.warning(f"OpenAI API error generating culminated plan: {e}")
            return {
                "summary": " ".join(findings[:2]) if findings else "Agent analysis completed. Review individual outputs.",
                "recommendations": [
                    "Review all agent outputs for comprehensive assessment",
                    "Consider multidisciplinary tumor board discussion"
                ],
                "key_findings": findings[:5] if findings else []
            }
        except Exception as e:
            logger.warning(f"Error generating culminated plan: {e}")
            return {
                "summary": " ".join(findings[:2]) if findings else "Agent analysis completed.",
                "recommendations": [
                    "Review all agent outputs for comprehensive assessment",
                    "Consider multidisciplinary tumor board discussion"
                ],
                "key_findings": findings[:5] if findings else []
            }


