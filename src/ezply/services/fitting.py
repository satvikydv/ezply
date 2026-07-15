import json
import os
from anthropic import Anthropic

class FitScorer:
    def __init__(self):
        # Assumes ANTHROPIC_API_KEY is in environment
        self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.model = "claude-3-5-sonnet-20241022" # Recommended standard model for this type of task

    def score(self, resume_text: str, job_description: str) -> dict:
        """
        Calls Claude API to score the job fit.
        Returns a dict matching the PRD schema:
        {
          "fit_score": int,
          "reasoning": str,
          "key_requirements": list[str],
          "concerns": list[str],
          "suggested_resume_emphasis": list[str]
        }
        """
        if not self.client.api_key:
            # Fallback or dummy if no API key
            return {
                "fit_score": 0,
                "reasoning": "No Anthropic API key found.",
                "key_requirements": [],
                "concerns": [],
                "suggested_resume_emphasis": []
            }

        prompt = f"""
You are an expert technical recruiter and AI assistant. Please evaluate the following job description against the provided resume.
Output your evaluation as a strict JSON object matching this schema, with no other text:
{{
  "fit_score": integer (0 to 100),
  "reasoning": "1-2 sentence explanation of the score",
  "key_requirements": ["list of main requirements from the job"],
  "concerns": ["list of potential mismatch concerns based on resume vs job"],
  "suggested_resume_emphasis": ["list of things from the resume to highlight for this job"]
}}

<job_description>
{job_description}
</job_description>

<resume>
{resume_text}
</resume>
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            # Extract JSON block if surrounded by markdown, or parse raw
            response_text = message.content[0].text
            # Basic cleanup in case Claude adds markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
                
            return json.loads(response_text)
        except Exception as e:
            return {
                "fit_score": 0,
                "reasoning": f"Error calling LLM: {str(e)}",
                "key_requirements": [],
                "concerns": [],
                "suggested_resume_emphasis": []
            }
