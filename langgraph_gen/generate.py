#!/usr/bin/env python3
"""LangGraph Agent Code Generator CLI"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Any, Callable, Literal, Set, Optional
from pprint import pprint
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

def format_strings(_dict: dict) -> dict:
    for key in _dict.keys():
        val = _dict[key]
        if isinstance(val, str):
            _dict[key] = val.format(**_dict)
    return _dict

def parse_import_str(import_str: str) -> tuple[str|None, str]:
    """Parse an import string into a module and object."""
    if (import_str) and "." in import_str:
        *module_parts, object_name = import_str.rsplit(".", 1)
    else:
        module_parts = None
        object_name = import_str
    module = ".".join(module_parts) if module_parts else None
    return module, object_name

def snake_to_class_name(snake_str: str) -> str:
    """Convert a snake case string to a class name."""
    return "".join(word.capitalize() for word in snake_str.split("_"))

def update_graph_name(spec: dict) -> str:
    """Update the name of the agent."""
    name = spec.get("name") or spec.get("graph_name")
    if not name:
        language = spec.get("language", "python")
        if language == "python":
            name = "create_agent"
        elif language == "typescript":
            name = "createAgent"
        else:
            raise ValueError(f"Invalid language: {language}")
    spec["name"] = name
    spec["graph_name"] = name
    return name

def update_graph_imports(spec: dict, imports: dict) -> dict:
    graph_import_keys = ["state", "input_state", "output_state", "config", "runtime_config"]
    for key in graph_import_keys:
        full_key = f"graph_{key}_type"
        val = spec.get(full_key) or spec.get(key) or snake_to_class_name(key)
        module, object_name = parse_import_str(val)
        if module:
            imports[module].append(object_name)
        else:
            imports[object_name] = None
        spec[full_key] = object_name
    return imports

def update_type_imports(spec: dict, imports: dict) -> dict:
    for import_dict in spec.get("imports", []):
        module = import_dict["module"]
        imports[module].extend(import_dict["objects"])
    spec["imports"] = imports
    return imports

def update_nodes(spec: dict) -> dict:
    """Add an id to each node in the spec which will be used as a machine name."""
    formatted_nodes = []
    for i, node in enumerate(spec.get("nodes", [])):
        # Set the node id to be a "machine name" if not provided
        # convert any non alpha-numeric characters to underscores
        node_name = node.get("name") or node.get("node_name", f"Node{i}")
        node["name"] = node["node_name"] = node_name
        node["id"] = node["node_id"] = re.sub(r"\W", "_", node_name)

        node["node_type"] = node.get("type") or node.get("node_type", "base")
        node["node_state_type"] = node.get("state_type") or node.get("node_state_type", "NodeState")
        node["overrides"] = node.get("overrides", [])
        if "all" in node["overrides"]:
            node["overrides"] = ["all"]
        formatted_nodes.append(format_strings(node))
    spec["nodes"] = formatted_nodes
    return spec


def _update_spec(spec: dict) -> dict:
    format_strings(spec)
    imports = defaultdict(list)
    update_graph_imports(spec, imports)
    update_type_imports(spec, imports)
    update_nodes(spec)
    spec["version"] = __version__
    print("--------------------------------")
    pprint(spec)
    print("--------------------------------")
    return spec


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
        modules: If known, the module name to import the graph from.
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
    _update_spec(spec) # Add machine names to the nodes
    # graph_name = update_graph_name(spec, language)
    env = SandboxedEnvironment(
        loader=jinja2.BaseLoader, trim_blocks=True, lstrip_blocks=True
    )

    generated = {}
    for template_type, template_path in templates.items():
        try:
            if template_type in TEMPLATE_TYPES:
                template_path = get_template_path(language, template_type, template_path)
                template = env.from_string(template_path.read_text())
            else:
                raise ValueError(f"Invalid template type: {template_type}")

            code = template.render(**spec)
            generated[template_type] = code
        except jinja2.TemplateError as e:
            raise AssertionError(
                f"Error rendering template {template_path}: {str(e)}",
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
