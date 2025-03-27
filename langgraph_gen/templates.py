"""Template management for LangGraph code generation."""

from pathlib import Path
from typing import List, Dict, Literal, Optional
from functools import lru_cache
from collections import defaultdict

# Template location
ASSETS =  Path(__file__).parent / "assets"


Language = Literal["python", "typescript"]
TemplateType = Literal["stub", "implementation", "state", "config"]
LANGUAGES: list[Language] = ["python", "typescript"]
TEMPLATE_TYPES: list[TemplateType] = ["stub", "implementation", "state", "config"]


@lru_cache(maxsize=1)
def get_available_templates() -> Dict[Language, Dict[TemplateType, List[Path]]]:
    """Get all available templates grouped by language.
    
    Returns:
        Dict mapping language to list of template types
    """
    result = {}
    for lang in LANGUAGES:
        result[lang] = defaultdict(list)
        for template_type in TEMPLATE_TYPES:
            for template_file in (ASSETS / lang / template_type).rglob("*.j2"):
                result[lang][template_type].append(template_file)   
    return result

def list_templates() -> str:
    """List all available templates in a user-friendly format.
    
    Returns:
        Formatted string listing all templates
    """
    templates = get_available_templates()
    
    output = ["Available templates:"]
    
    for language, template_list in templates.items():
        output.append(f"\n{language.capitalize()} templates:")
        for template_type, templates in sorted(template_list.items()):
            output.append(f"\t{template_type.capitalize()} templates:")
            for template in sorted(templates):
                output.append(f"\t\t- {template.name}")
    
    return "\n".join(output)

def get_template_path(
        language: Language, 
        template_type: TemplateType,
        template: str
    ) -> Path:
    """Get the path to a template file.
    
    Args:
        language: The target language
        template_type: The type of template
        custom_template: Optional custom template name
        
    Returns:
        The template file path
    """
    if not template.endswith(".j2"):
        template += ".j2"

    if (template_path := Path(template)).exists():
        return template_path
    
    template_path = ASSETS / language / template_type / template
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template '{template}' not found in {template_path}")
    
    return template_path