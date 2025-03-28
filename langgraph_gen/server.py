"""HTTP server for langgraph-gen."""

from pathlib import Path
from typing import Optional, Literal, Dict, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langgraph_gen._version import __version__
from langgraph_gen.generate import generate_from_spec
from langgraph_gen.templates import get_available_templates, TemplateType, TEMPLATE_TYPES, Language

app = FastAPI(
    title="LangGraph Generator API",
    description="Generate LangGraph agent base classes from YAML specs via HTTP",
    version=__version__,
)

class GenerateRequest(BaseModel):
    """Request model for code generation."""
    spec: str
    language: Literal["python", "typescript"] = "python"
    output_files: Dict[TemplateType, str] = {}
    templates: Dict[TemplateType, str] = {}
    only: Optional[List[str]] = None
    skip: Optional[List[str]] = None

class GenerateResponse(BaseModel):
    """Response model for code generation."""
    files: Dict[TemplateType, str]

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate code from a YAML specification.
    
    Args:
        request: The generation request containing the spec and options
        
    Returns:
        Generated code files
    """
    try:
        # Filter templates based on only/skip
        templates = {}
        for template_type in TEMPLATE_TYPES:
            if request.only and template_type not in request.only:
                continue
            if request.skip and template_type in request.skip:
                continue
            templates[template_type] = request.templates.get(template_type, "default")

        # Generate the code
        generated = generate_from_spec(
            request.spec,
            "yaml",
            templates=templates,
            language=request.language,
            modules={"graph": "graph"}  # Default module name since we're not dealing with files
        )
        
        return GenerateResponse(files=generated)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class Template(BaseModel):
    name: str
    path: str
    language: Language
    template_type: TemplateType
    content: str

class TemplatesResponse(BaseModel):
    templates: List[Template]

@app.get("/templates", response_model=TemplatesResponse)
async def get_templates() -> TemplatesResponse:
    """List available templates.
    
    Returns:
        List of available templates
    """
    available_templates = get_available_templates()
    templates = []
    for language, template_list in available_templates.items():
        for template_type, template_paths in template_list.items():
            for template_path in template_paths:
                content = template_path.read_text()
                templates.append(Template(
                    name=template_path.name, path=str(template_path), 
                    language=language, template_type=template_type, content=content
                ))
    return TemplatesResponse(templates=templates)