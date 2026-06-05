import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, Runner
from jinja2 import Environment, FileSystemLoader, TemplateNotFound


PROMPTS_DIR = Path(__file__).parent / "prompt_templates"
CONDITIONAL_ANALYSIS_MODEL = "gpt-3.5-turbo"  # Model for condition analysis used to prepare prompts
GENERATOR_MODEL = "gpt-4o-mini" # Model for output generation

# Map output section names to their prompt template files.
# Sections not listed here will default to "generic_section.j2"
SECTION_TEMPLATE_MAP: dict[str, str] = {
    "introduction": "introduction.j2",
    "summary": "summary.j2",
}


@dataclass
class DocumentSection:
    """A single section of the input document."""
    name: str  # Section header e.g. "introduction", "background", "summary"
    text: str  # Section text extracted from the source document, which may contain key info for generation


@dataclass
class ResolvedSection:
    """A document section after condition analysis and prompt rendering."""
    section: DocumentSection
    conditions: dict[str, Any]  # Resolved boolean/value flags, either from heuristics or LLM analysis
    rendered_prompt: str  # Final prompt ready to send to the LLM


@dataclass
class GeneratedDocument:
    """
    The compiled output document, with all expected sections from an output template.

    The keys of the `sections` dict correspond to section names, and the values are the LLM-generated content 
    for each section.
    """
    sections: dict[str, str] = field(default_factory=dict)  # section_name -> llm_output

    def to_dict(self) -> dict[str, str]:
        """Helper method to convert the GeneratedDocument to a plain dict for easier consumption."""
        return dict(self.sections)


class PromptLoader:
    """Loads and renders Jinja2 prompt templates from the local prompts directory."""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.env = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, variables: dict[str, Any]) -> str:
        """
        Render the specified template with the given variables.
        If the template is not found, falls back to a generic section template.
        
        :param template_name: The name of the template file to load (e.g. "introduction.j2")
        :param variables: A dict of variables to pass to the template for rendering
        
        :return: The rendered prompt string
        """
        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound:
            # Fall back to the generic section template
            print(f"[PromptLoader] Template '{template_name}' not found, using generic_section.j2")
            template = self.env.get_template("generic_section.j2")
        return template.render(**variables)


class ConditionAnalyzer:
    """
    Analyzes a document section and resolves if-then conditions that control
    prompt branching. Each condition method receives the DocumentSection and 
    returns a value that is injected into the Jinja2 template context.

    The `analyze_with_llm` method sends the section text to a small LLM to
    determine conditions dynamically — useful when the logic is too complex
    for simple heuristics.
    """

    def __init__(self, runner: Runner):
        self._runner = runner
        self._loader = PromptLoader()

    # -- Heuristic conditions (no LLM calls) ---------------------------

    def _condition_word_limit(self, section: DocumentSection) -> int:
        """
        Applies a word limit condition based on the length of the input section text.

        :param section: The document section to analyze.

        :return: An integer word limit to be used in the prompt template.
        """
        input_word_count = len(section.text.split())
        if input_word_count < 50:
            return 200
        if input_word_count < 150:
            return 400
        return 600

    # -- Conditions requiring LLM calls to determine -----------------------

    async def analyze_with_llm(self, section: DocumentSection) -> dict[str, Any]:
        """
        Ask a small LLM to resolve conditions for this section. The LLM returns a 
        JSON object with boolean/value flags that are then merged into the Jinja2 template context.

        :param section: The document section to analyze.

        :return: A dict of condition names to their resolved values. These are 
            inserted into the Jinja2 template context for prompt rendering.
        """
        # Load the condition analysis prompt template and render it with the section text
        prompt = self._loader.render(
            "condition_analysis.j2",
            {"section_text": section.text},
        )

        # Run the prompt through the LLM to get condition values
        agent = Agent(
            name="ConditionAnalyzer",
            model=CONDITIONAL_ANALYSIS_MODEL,
            instructions="You are a document analysis assistant. Follow the user's instructions exactly.",
        )
        result = await self._runner.run(agent, prompt)
        raw = result.final_output.strip()

        # Try to parse the LLM response as JSON. If it fails, log a warning and return an empty dict (no conditions).
        # Expecting the LLM to return a JSON object like: {"include_chart": true, "focus_on_trends": false}
        parse_error = None
        try:
            conditions = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[ConditionAnalyzer] Could not parse LLM response as JSON, using defaults. Raw: {raw!r}")
            parse_error = str(e)
            conditions = {}
 
        # Dump intermediary debug file for this section
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        debug = {
            "section": section.name,
            "section_text": section.text,
            "llm_raw_response": raw,
            "parsed_conditions": conditions,
            **({"parse_error": parse_error} if parse_error else {}),
        }
        debug_path = output_dir / f"conditions_{section.name}.json"
        debug_path.write_text(json.dumps(debug, indent=2))
        print(f"[ConditionAnalyzer] Debug written to {debug_path}")

        return conditions

    async def resolve(self, section: DocumentSection) -> dict[str, Any]:
        """
        Merge heuristic and LLM-derived conditions into a single context dict.

        :param section: The document section to analyze.

        :return: A dict of condition names to their resolved values. These are 
            inserted into the Jinja2 template context for prompt rendering.
        """
        # Start with heuristic conditions
        conditions: dict[str, Any] = {
            "word_limit": self._condition_word_limit(section),
            # Add more heuristic conditions here
        }

        # Overlay with LLM-derived conditions
        llm_conditions = await self.analyze_with_llm(section)
        conditions.update(llm_conditions)

        return conditions


class DocumentGenerator:
    """
    Orchestrates the full generation pipeline for a list of document sections.
    """

    def __init__(self):
        self._runner = Runner()
        self._loader = PromptLoader()
        self._analyzer = ConditionAnalyzer(self._runner)

    async def _prepare_section(self, section: DocumentSection) -> ResolvedSection:
        """
        For a given document section:
          1. Resolve conditions using the ConditionAnalyzer (which may call an LLM)
          2. Render the appropriate Jinja2 prompt template with the section text and resolved conditions.
        
        :param section: The document section to prepare.

        :return: A ResolvedSection containing the original section, the resolved conditions, and the rendered prompt.
        """
        print(f"[Prepare] Resolving conditions for section: '{section.name}'")
        # Resolve conditions (this may involve LLM calls)
        conditions = await self._analyzer.resolve(section)

        # Render the prompt template for this section, injecting the section text and resolved conditions
        template_name = SECTION_TEMPLATE_MAP.get(section.name, "generic_section.j2")
        variables = {"section_text": section.text, **conditions}
        rendered_prompt = self._loader.render(template_name, variables)

        return ResolvedSection(
            section=section,
            conditions=conditions,
            rendered_prompt=rendered_prompt,
        )

    async def _generate_section(self, resolved: ResolvedSection) -> tuple[str, str]:
        """
        Get the LLM output for a single resolved section by sending the rendered prompt to the OpenAI Agents SDK.

        :param resolved: The ResolvedSection containing the original section, resolved conditions, and rendered prompt.

        :return: A tuple of (section_name, llm_output) where llm_output is the generated content for this section.
        """
        section_name = resolved.section.name
        print(f"[Generate] Sending prompt for section: '{section_name}'")

        # Create an agent for this section and run the rendered prompt through it to get the generated content
        agent = Agent(
            name=f"SectionWriter_{section_name}",
            model=GENERATOR_MODEL,
            instructions="You are a professional document writer. Follow the user's instructions exactly and return only the requested content.",
        )
        result = await self._runner.run(agent, resolved.rendered_prompt)

        # Return the section name and the LLM output (stripping whitespace)
        return section_name, result.final_output.strip()

    def _compile(self, outputs: list[tuple[str, str]]) -> GeneratedDocument:
        """
        Compile the list of (section_name, llm_output) tuples into a single GeneratedDocument.

        :param outputs: A list of tuples where each tuple contains a section name and its 
            corresponding LLM-generated content.

        :return: A GeneratedDocument instance containing all sections and their generated content.
        """
        doc = GeneratedDocument()
        # Iterate through the outputs and populate the sections of the GeneratedDocument
        for section_name, llm_output in outputs:
            doc.sections[section_name] = llm_output
        return doc

    async def generate(self, sections: list[DocumentSection]) -> GeneratedDocument:
        """
        Runs the full pipeline:
          1. Prepare all sections by resolving conditions from the source text and rendering 
             prompts based on the conditions.
          2. Concurrently generate all sections of the doc using a LLM call (OpenAI Agent)
          3. Compile the LLM responses for each section into a GeneratedDocument
        """
        print("\n=== Step 1: Preparing prompts for sections ===")
        prepared = await asyncio.gather(
            *[self._prepare_section(s) for s in sections]
        )

        print("\n=== Step 2: Generating document sections ===")
        outputs = await asyncio.gather(
            *[self._generate_section(p) for p in prepared]
        )

        print("\n=== Step 3: Compiling finished document ===")
        document = self._compile(list(outputs))

        return document


async def main():
    """
    Main function to demonstrate the document generation pipeline with sample input sections.
    """
    # -- Sample input: list of document sections ----------------------------
    sections = [
        DocumentSection(
            name="introduction",
            text=(
                "This report covers Q3 performance for Acme Corp's enterprise division. "
                "Revenue grew 12% YoY driven by new SaaS contracts. "
                "Headcount increased from 340 to 390."
            ),
        ),
        DocumentSection(
            name="market_analysis",
            text=(
                "Key trends: AI adoption in SMBs, consolidation among mid-market vendors, "
                "rising infrastructure costs. Competitors include Globex and Initech. "
                "Opportunity in underserved healthcare vertical."
            ),
        ),
        DocumentSection(
            name="summary",
            text=(
                "Strong quarter overall. Focus areas for Q4: close healthcare pipeline, "
                "reduce churn in SMB segment, launch v2 of core product."
            ),
        ),
    ]

    generator = DocumentGenerator()
    document = await generator.generate(sections)

    with open("output/generated_document.json", "w") as f:
        json.dump(document.to_dict(), f, indent=2)

    return document.to_dict()


if __name__ == "__main__":
    asyncio.run(main())
