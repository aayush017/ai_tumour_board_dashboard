"""
Agent Orchestrator Service
Orchestrates all four agents (radiology, clinical, pathology, tumor_board) 
and combines their outputs into a unified response.
"""

from typing import Dict, Any, Optional
from openai import OpenAI
import os
import sys

# Add backend directory to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from radiology_agent import RadiologyAgent, OpenAILLM
from clinical_agent import ClinicalDataAgent
from pathology_agent import PathologyMolecularAgent
from tumor_board_summary_agent import TumorBoardNotesAgent


class AgentOrchestrator:
    """Orchestrates all four agents and combines their outputs."""

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize all agents with shared OpenAI client."""
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
        
        # Initialize agents
        self.radiology_llm = OpenAILLM(api_key=api_key_value)
        self.radiology_agent = RadiologyAgent(llm=self.radiology_llm)
        self.clinical_agent = ClinicalDataAgent(openai_api_key=api_key_value)
        self.pathology_agent = PathologyMolecularAgent(openai_api_key=api_key_value)
        self.tumor_board_agent = TumorBoardNotesAgent(client=self.client)

    def process_all(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process patient data through all four agents and return combined results.
        
        Args:
            patient_data: Full patient data including demographics, clinical, lab_data,
                         radiology, pathology, tumor_board, treatment_history
        
        Returns:
            Combined response with all agent outputs and a culminated plan of action
        """
        results = {
            "radiology": None,
            "clinical": None,
            "pathology": None,
            "tumor_board": None,
            "errors": {}
        }

        # 1. Process Radiology
        try:
            radiology_section = patient_data.get("radiology", {})
            if radiology_section and radiology_section.get("studies"):
                results["radiology"] = self.radiology_agent.process(radiology_section)
        except Exception as e:
            results["errors"]["radiology"] = str(e)

        # 2. Process Clinical
        try:
            clinical_input = {
                "demographics": patient_data.get("demographics", {}),
                "clinical": patient_data.get("clinical", {}),
                "lab_data": patient_data.get("lab_data", {})
            }
            results["clinical"] = self.clinical_agent.process(clinical_input)
        except Exception as e:
            results["errors"]["clinical"] = str(e)

        # 3. Process Pathology
        try:
            pathology_input = {"pathology": patient_data.get("pathology", {})}
            results["pathology"] = self.pathology_agent.process(pathology_input)
        except Exception as e:
            results["errors"]["pathology"] = str(e)

        # 4. Process Tumor Board
        try:
            tumor_board_data = patient_data.get("tumor_board", {})
            treatment_history_data = patient_data.get("treatment_history", {})
            if tumor_board_data or treatment_history_data:
                results["tumor_board"] = self.tumor_board_agent.run(
                    tumor_board_data, 
                    treatment_history_data
                )
        except Exception as e:
            results["errors"]["tumor_board"] = str(e)

        # Generate culminated plan of action
        culminated_plan = self._generate_culminated_plan(results)

        return {
            "agent_responses": {
                "radiology": results["radiology"],
                "clinical": results["clinical"],
                "pathology": results["pathology"],
                "tumor_board": results["tumor_board"]
            },
            "culminated_plan_of_action": culminated_plan,
            "agent_metadata": {
                "errors": results["errors"] if results["errors"] else None,
                "radiology_confidence": results["radiology"].get("radiology_summary", {}).get("agent_metadata", {}).get("radiology_agent_confidence") if results["radiology"] else None,
                "clinical_confidence": results["clinical"].get("agent_metadata", {}).get("clinical_agent_confidence") if results["clinical"] else None,
                "pathology_confidence": results["pathology"].get("pathology_summary", {}).get("agent_metadata", {}).get("pathology_agent_confidence") if results["pathology"] else None,
            }
        }

    def _generate_culminated_plan(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a culminated plan of action based on all agent outputs.
        Uses LLM to synthesize recommendations from all agents.
        """
        # Extract key findings from each agent
        findings = []
        
        if results.get("radiology"):
            rad_summary = results["radiology"].get("radiology_summary", {})
            if rad_summary.get("radiology_interpretation"):
                findings.append(f"Radiology: {rad_summary['radiology_interpretation']}")
        
        if results.get("clinical"):
            clinical_summary = results["clinical"].get("clinical_summary", {})
            if clinical_summary.get("clinical_interpretation"):
                findings.append(f"Clinical: {clinical_summary['clinical_interpretation']}")
            # Add key scores
            derived = clinical_summary.get("derived_scores", {})
            cp = derived.get("Child_Pugh", {})
            if cp.get("class"):
                findings.append(f"Child-Pugh: {cp['class']} (score: {cp.get('score', 'N/A')})")
            if derived.get("MELD_Na"):
                findings.append(f"MELD-Na: {derived['MELD_Na']}")
        
        if results.get("pathology"):
            path_summary = results["pathology"].get("pathology_summary", {})
            if path_summary.get("pathology_interpretation"):
                findings.append(f"Pathology: {path_summary['pathology_interpretation']}")
        
        if results.get("tumor_board"):
            tb_summary = results["tumor_board"].get("notes_summary", {})
            if tb_summary.get("tumor_board_text"):
                findings.append(f"Tumor Board: {tb_summary['tumor_board_text']}")

        # If no findings, return empty plan
        if not findings:
            return {
                "summary": "Insufficient data to generate a comprehensive plan.",
                "recommendations": [],
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
        except Exception as e:
            # Fallback plan
            return {
                "summary": " ".join(findings[:2]) if findings else "Data processed successfully.",
                "recommendations": [
                    "Review all agent outputs for comprehensive assessment",
                    "Consider multidisciplinary tumor board discussion"
                ],
                "key_findings": findings[:5]
            }

