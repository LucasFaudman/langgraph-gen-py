"""Entrypoint script."""

import argparse
import sys
from pathlib import Path
from typing import Optional, Literal

from langgraph_gen._version import __version__
from langgraph_gen.generate import generate_from_spec
from langgraph_gen.templates import list_templates, TemplateType, TEMPLATE_TYPES, Language


def print_error(message: str) -> None:
    """Print error messages with visual emphasis.

    Args:
        message: The error message to display
    """
    if sys.stderr.isatty():
        # Use colors for terminal output
        sys.stderr.write(f"\033[91mError: {message}\033[0m\n")
    else:
        # Plain text for non-terminal output
        sys.stderr.write(f"Error: {message}\n")


def _rewrite_path_as_import(path: Path) -> str:
    """Rewrite a path as an import statement."""
    return ".".join(path.with_suffix("").parts)


def _generate(
    input_file: Path,
    *,
    language: Literal["python", "typescript"],
    output_files: dict[TemplateType, Path] = {},
    templates: dict[TemplateType, str] = {},
) -> dict[TemplateType, Path]:
    """Generate agent code from a YAML specification file.

    Args:
        input_file (Path): Input YAML specification file
        language (Literal["python", "typescript"]): Language to generate code for
        output_files (dict[TemplateType, Path]): Output file paths for the graph, implementation, state, and config
        templates (dict[str, str]): Custom templates for the graph, implementation, state, and config

    Returns:
        dict[TemplateType, Path]: Paths to the generated files
    """
    if language not in ["python", "typescript"]:
        raise NotImplementedError(
            f"Unsupported language: {language}. Use one of 'python' or 'typescript'"
        )
    suffix = ".py" if language == "python" else ".ts"
    input_stem = input_file.stem
    
    for template_type in TEMPLATE_TYPES:
        if template_type not in output_files:
            output_files[template_type] = input_file.with_name(f"{template_type}{suffix}")
    
    # Get the implementation relative to the output path
    graph_module = _rewrite_path_as_import(
        output_files["graph"].relative_to(output_files["graph"].parent)
    )

    spec_as_yaml = input_file.read_text()
    generated = generate_from_spec(
        spec_as_yaml,
        "yaml",
        templates=templates,
        language=language,
        modules={"graph": graph_module}
    )
    _output_files = {}
    for template_type, code in generated.items():
        output_files[template_type].write_text(code)
        _output_files[template_type] = output_files[template_type]

    # Return the created files for reporting
    return _output_files


def main() -> None:
    """Langgraph-gen CLI entry point."""
    # Define examples text separately with proper formatting
    examples = """
Examples:
  # Generate Python code from a YAML spec
  langgraph-gen spec.yml

  # Generate TypeScript code from a YAML spec
  langgraph-gen spec.yml --language typescript

  # Generate with custom output paths
  langgraph-gen spec.yml -o custom_output.py --implementation custom_impl.py
  
  # List available templates
  langgraph-gen --list-templates
  
  # Generate with custom templates
  langgraph-gen spec.yml --graph-template py-class-graph.j2 --impl-template py-impl-graph.j2
"""

    # Use RawDescriptionHelpFormatter to preserve newlines in epilog
    parser = argparse.ArgumentParser(
        description="Generate LangGraph agent base classes from YAML specs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=examples,
    )
    parser.add_argument("input", type=Path, help="Input YAML specification file", nargs="?")
    parser.add_argument(
        "-l",
        "--language",
        type=str,
        default="python",
        help="Language to generate code for (python, typescript)",
    )

    parser.add_argument(
        "--only",
        type=str,
        nargs="*",
        help="Only generate the specified template type",
    )
    parser.add_argument(
        "--skip",
        type=str,
        nargs="*",
        help="Skip the specified template type",
    )

    
    
    for template_type in TEMPLATE_TYPES:
        parser.add_argument(
            f"-{template_type[0]}O",
            f"--{template_type}-outfile",
            type=Path,
            help=f"Output file path for the {template_type}",
        )

    for template_type in TEMPLATE_TYPES:
        parser.add_argument(
            f"-{template_type[0]}T",
            f"--{template_type}-template",
            type=str,
            help=f"Custom template to use for the {template_type}",
        )

    parser.add_argument(
        "-L",
        "--list-templates",
        action="store_true",
        help="List available templates",
    )    

    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Custom error handling for argparse
    try:
        args = parser.parse_args()
    except SystemExit as e:
        # If there's a parse error (exit code != 0), show the full help
        if e.code != 0:
            # Create a custom parser without formatter to avoid showing usage twice
            custom_help_parser = argparse.ArgumentParser(
                description=parser.description,
                formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog=parser.epilog,
                add_help=False,
                usage=argparse.SUPPRESS,  # Suppress the usage line
            )
            # Add the same arguments
            for action in parser._actions:
                if action.dest != "help":  # Skip the help action
                    custom_help_parser._add_action(action)

            # Print full help without the usage line (which was already printed by argparse)
            print()
            custom_help_parser.print_help()

            # Add error message using our helper function
            print_error("Invalid arguments")
        sys.exit(e.code)
        
    # Handle listing templates
    if args.list_templates:
        print(list_templates())
        sys.exit(0)

    # Check if input file is provided when not listing templates
    if not args.input:
        print_error("Input file is required unless --list-templates is specified")
        sys.exit(1)
        
    # Check if input file exists
    if not args.input.exists():
        print_error(f"Input file {args.input} does not exist")
        sys.exit(1)
    
    output_files = {}
    templates = {}
    suffix = ".py" if args.language == "python" else ".ts"
    for template_type in TEMPLATE_TYPES:
        if args.only and template_type not in args.only:
            continue
        if args.skip and template_type in args.skip:
            continue
        if outfile := getattr(args, f"{template_type}_outfile"):
            output_files[template_type] = outfile
        else:
            output_files[template_type] = args.input.with_name(f"{template_type}{suffix}")
        if template := getattr(args, f"{template_type}_template"):
            templates[template_type] = template
        else:
            templates[template_type] = "default"

    # Generate the code
    try:
        output_files = _generate(
            input_file=args.input,
            output_files=output_files,
            templates=templates,
            language=args.language,
        )
        # Check if stdout is a TTY to use colors and emoji
        if sys.stdout.isatty():
            print("\033[32m✅ Successfully generated files:\033[0m")
            for template_type, file in output_files.items():
                print(f"\033[32m📄 {template_type.capitalize()} file: \033[0m {file}")
        else:
            print("Successfully generated files:")
            for template_type, file in output_files.items():
                print(f"- {template_type.capitalize()} file: {file}")
    except Exception as e:
        # Use our helper function for consistent error formatting
        print_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
