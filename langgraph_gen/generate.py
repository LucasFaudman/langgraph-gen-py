#!/usr/bin/env python3
"""LangGraph Agent Code Generator CLI"""

import json
import re
from pathlib import Path
from typing import Any, Callable, Literal, Set, Optional

import jinja2
import yaml
from jinja2.sandbox import SandboxedEnvironment
from langgraph.graph import StateGraph, START, END

from langgraph_gen._version import __version__
from langgraph_gen.templates import get_template_path, TemplateType, Language, TEMPLATE_TYPES

# Path references
HERE = Path(__file__).parent
ASSETS = HERE / "assets"

class InvalidSpec(Exception):
    """Invalid spec."""


def _validate_spec(spec: Any) -> None:
    """Raise an error if the spec is invalid."""
    if not isinstance(spec, dict):
        raise InvalidSpec("Specification must be a top level dictionary.")
    required_fields = {"nodes", "edges"}
    if not required_fields.issubset(spec.keys()):
        missing = required_fields - spec.keys()
        raise ValueError(f"Missing required fields in spec: {', '.join(missing)}")

    node_names = {n["name"] for n in spec["nodes"]}
    for edge in spec["edges"]:
        if edge["from"] not in node_names and edge["from"] != START:
            raise ValueError(f"Edge source node '{edge['from']}' not defined in nodes")
        if "to" in edge:
            if edge["to"] not in node_names and edge["to"] != END:
                raise ValueError(
                    f"Edge target node '{edge['to']}' not defined in nodes"
                )


PATTERN = re.compile(r"\W")


def _update_spec(spec: dict) -> None:
    """Add an id to each node in the spec which will be used as a machine name."""
    for node in spec["nodes"]:
        # Set the node id to be a "machine name" if not provided
        # convert any non alpha-numeric characters to underscores
        node["id"] = PATTERN.sub("_", node["name"])

def _update_name(spec: dict, language: Language) -> str:
    """Update the name of the agent."""
    if "name" not in spec:
        if language == "python":
            spec["name"] = "create_agent"
        elif language == "typescript":
            spec["name"] = "createAgent"
        else:
            raise ValueError(f"Invalid language: {language}")
    return spec["name"]

def generate_from_spec(
    spec_str: str,
    format_: Literal["yaml", "json"],
    templates: dict[TemplateType, str],
    *,
    language: Language = "python",
    modules: Optional[dict[TemplateType, str]] = None,
    names: Optional[dict[TemplateType, str]] = None,
) -> dict[TemplateType, str]:
    """Generate agent code from a YAML specification file.

    Args:
        spec_str: Specification encoded as a string
        format_: Format of the specification
        templates: Sequence of templates to generate
        language: Language to generate code for
        modules: If known, the module name to import the stub from.
            This will be known in the CLI.
    Returns:
        dict[TemplateType, str]: Generated code files.
    """
    if format_ == "yaml":
        try:
            spec = yaml.safe_load(spec_str)
        except Exception:
            raise InvalidSpec("Invalid YAML spec.")
    elif format_ == "json":
        try:
            spec = json.loads(spec_str)
        except Exception:
            raise InvalidSpec("Invalid JSON spec.")
    else:
        raise ValueError(f"Invalid format: {format_}")

    _validate_spec(spec)
    # Add machine names to the nodes
    _update_spec(spec)
    stub_name = _update_name(spec, language)

    env = SandboxedEnvironment(
        loader=jinja2.BaseLoader, trim_blocks=True, lstrip_blocks=True
    )

    _modules = {}
    _names = {"stub_name": stub_name}
    for template_type in TEMPLATE_TYPES:
        if modules and template_type in modules:
            _modules[f"{template_type}_module"] = modules[template_type]
        if names and template_type in names:
            _names[f"{template_type}_name"] = names[template_type]

    if "builder_name" not in _names:
        _names["builder_name"] = spec.get("builder_name", "builder")
    if "compiled_name" not in _names:
        _names["compiled_name"] = spec.get("compiled_name", "graph")
    for spec_key in ["config", "state", "input", "output", "implementation"]:
        if (spec_val := spec.get(spec_key)) and "." in spec_val:
            *module_parts, name = spec_val.rsplit(".", 1)
        else:
            module_parts = None
            name = spec_val

        module_key = f"{spec_key}_module"
        if module_parts and not _modules.get(module_key):
            _modules[module_key] = ".".join(module_parts)
        
        name_key = f"{spec_key}_name"
        if name and not _names.get(name_key):
            _names[name_key] = name

    generated = {}

    for template_type, template_path in templates.items():
        try:
            if template_type in TEMPLATE_TYPES:
                template_path = get_template_path(language, template_type, template_path)
                template = env.from_string(template_path.read_text())
            else:
                raise ValueError(f"Invalid template type: {template_type}")

            code = template.render(
                nodes=spec["nodes"],
                edges=spec["edges"],
                entrypoint=spec.get("entrypoint", None),
                version=__version__,
                **_modules,
                **_names,
            )
            generated[template_type] = code
        except jinja2.TemplateError as e:
            raise AssertionError(
                f"Error rendering template: {str(e)}",
            )

    return generated


def _add_to_graph(
    state_graph: StateGraph,
    spec: str,
    implementations: list[tuple[str, Callable]],
) -> None:
    """Add edges and implementations to the state graph, updating it in place.

    Args:
        state_graph (StateGraph): The state graph to update.
        spec: Specification as a YAML string
        implementations (list[tuple[str, Callable]]): The list of implementations.
    """
    spec_ = yaml.safe_load(spec)

    # Declare the state graph
    if not isinstance(spec_, dict):
        raise TypeError(
            f"Specification must be a top level dictionary. Found: {type(spec_)}"
        )

    # Identify all node implementations by scanning the edges
    if "edges" not in spec_:
        raise ValueError("Missing key 'edges' in spec.")

    edges = spec_["edges"]
    found_nodes: Set[str] = set()

    for edge in edges:
        if "from" in edge:
            found_nodes.add(edge["from"])
        if "to" in edge:
            found_nodes.add(edge["to"])
        if "condition" in edge:
            found_nodes.add(edge["condition"])
        if "paths" in edge:
            if isinstance(edge["paths"], dict):
                found_nodes.update(edge["paths"].values())
            elif isinstance(edge["paths"], list):
                found_nodes.update(edge["paths"])
            else:
                raise TypeError(f"Invalid paths: {edge['paths']}")

    # Remove the end node from the edges since it's a special case
    found_nodes = found_nodes - {"__end__"}

    nodes_by_name = {name: implementation for name, implementation in implementations}
    found_implementations = set(nodes_by_name)

    missing_implementations = found_nodes - found_implementations

    if missing_implementations:
        raise ValueError(f"Missing implementations for : {missing_implementations}")

    for name, node in nodes_by_name.items():
        state_graph.add_node(name, node)

    for edge in spec_["edges"]:
        # It's a conditional edge
        if "condition" in edge:
            state_graph.add_conditional_edges(
                edge["from"],
                nodes_by_name[edge["condition"]],
                path_map=edge["paths"] if "paths" in edge else None,
            )
        else:
            # it's a directed edge
            state_graph.add_edge(edge["from"], edge["to"])

    # Set the entry point
    if "entrypoint" in spec_:
        state_graph.add_edge(START, spec_["entrypoint"])


def _add_to_graph_from_yaml(
    state_graph: StateGraph,
    spec: str,
    implementations: list[tuple[str, Callable]],
) -> None:
    """Add edges and implementations to the state graph, updating it in place.

    Args:
        state_graph (StateGraph): The state graph to update.
        spec: Specification as a YAML string
        implementations (list[tuple[str, Callable]]): The list of implementations.
    """
    spec_ = yaml.safe_load(spec)
    return _add_to_graph(
        state_graph,
        spec_,
        implementations,
    )
