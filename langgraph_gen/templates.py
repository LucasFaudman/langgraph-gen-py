"""Template management for LangGraph code generation."""

from pathlib import Path
from typing import List, Dict, Literal, Optional
from functools import lru_cache
from collections import defaultdict

# Template location
ASSETS =  Path(__file__).parent / "assets"


Language = str
TemplateType = str
LANGUAGES: list[Language] = ["python", "typescript"]
TEMPLATE_TYPES: list[TemplateType] = ["graph", "implementation", "state", "config"]

TEMPLATE_DIRS = [
    ASSETS,
]

def add_template_dir(template_dir: Path):
    TEMPLATE_DIRS.append(template_dir)
    for language_dir in template_dir.glob("*"):
        language = language_dir.name
        for template_type_dir in language_dir.glob("*"):
            template_type = template_type_dir.name
            for template_file in template_type_dir.glob("*.j2"):
                template = template_file.name
                if language not in LANGUAGES:
                    LANGUAGES.append(language)
                if template_type not in TEMPLATE_TYPES:
                    TEMPLATE_TYPES.append(template_type)
                
    
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
            for template_dir in TEMPLATE_DIRS:
                for template_file in (template_dir / lang / template_type).rglob("*.j2"):
                    result[lang][template_type].append(template_file)
    return result

def list_templates(
    language: Optional[Language] = None,
    template_types: Optional[List[TemplateType]] = None,
) -> str:
    """List all available templates in a user-friendly format.
    
    Returns:
        Formatted string listing all templates
    """
    templates = get_available_templates()
    
    output = ["Available templates:"]
    for language, template_list in templates.items():
        if language and language != language:
            continue
        output.append(f"\n{language.capitalize()} templates:")
        for template_type, templates in sorted(template_list.items()):
            if template_types and template_type not in template_types:
                continue
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
    
    # Check in all template dirs
    for template_dir in TEMPLATE_DIRS:
        if (template_path := template_dir / language / template_type / template).exists():
            return template_path
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template '{template}' not found in {template_path}")
    
    return template_path

# class TemplateManager:
#     def __init__(self, template_dirs: List[Path]):
#         self.template_dirs = template_dirs
#         if ASSETS not in template_dirs:
#             self.template_dirs.append(ASSETS)

#     def get_template_path(self, language: Language, template_type: TemplateType, template: str) -> Path:
#         for template_dir in self.template_dirs:
#             template_path = template_dir / language / template_type / template
#             if template_path.exists():
#                 return template_path
#         raise FileNotFoundError(f"Template '{template}' not found in {self.template_dirs}")

#     def get_template_names(self, language: Language, template_type: TemplateType) -> List[str]:
#         template_names = []
#         for template_dir in self.template_dirs:
#             template_path = template_dir / language / template_type
#             if template_path.exists():
#                 template_names.extend(template_path.glob("*.j2"))
#         return template_names

#     def get_template_types(self, language: Language) -> List[TemplateType]:
#         template_types = []
#         for template_dir in self.template_dirs:
#             template_path = template_dir / language
#             if template_path.exists() and template_path.is_dir() and template_path.glob("*.j2"):
#                 template_types.extend(template_path.glob("*.j2"))
#         return template_types

#     def get_templates_in_dir(self, template_dir: Path) -> Dict[Language, Dict[TemplateType, List[Path]]]:
#         templates = defaultdict(lambda: defaultdict(list))
#         for language_dir in filter(Path.is_dir, template_dir.glob("*")):
#             language = language_dir.name
#             for template_type_dir in filter(Path.is_dir, language_dir.glob("*")):
#                 template_type = template_type_dir.name
#                 templates[language][template_type].extend(template_type_dir.glob("*.j2"))
#         return templates

#     def get_available_templates(self) -> Dict[Language, Dict[TemplateType, List[Path]]]:
#         templates = defaultdict(lambda: defaultdict(list))
#         for template_dir in self.template_dirs:
#             _templates = self.get_templates_in_dir(template_dir)
#             for language, template_type_templates in _templates.items():
#                 for template_type, templates in template_type_templates.items():
#                     templates[language][template_type].extend(templates)
#         return templates