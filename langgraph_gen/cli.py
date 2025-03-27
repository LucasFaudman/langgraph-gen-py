"""Entrypoint script."""

import argparse
import sys
from pathlib import Path
from typing import Optional, Literal

from langgraph_gen._version import __version__
from langgraph_gen.generate import generate_from_spec
from langgraph_gen.templates import list_templates, TemplateType


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
        output_files (dict[TemplateType, Path]): Output file paths for the stub, implementation, state, and config
        templates (dict[str, str]): Custom templates for the stub, implementation, state, and config

    Returns:
        dict[TemplateType, Path]: Paths to the generated files
    """
    if language not in ["python", "typescript"]:
        raise NotImplementedError(
            f"Unsupported language: {language}. Use one of 'python' or 'typescript'"
        )
    suffix = ".py" if language == "python" else ".ts"
    input_stem = input_file.stem
    
    if "stub" not in output_files:
        output_files["stub"] = input_file.with_suffix(suffix)
    if "implementation" not in output_files:
        output_files["implementation"] = input_file.with_name(f"{input_stem}_impl{suffix}")
    if "state" not in output_files:
        output_files["state"] = input_file.with_name(f"{input_stem}_state{suffix}")
    if "config" not in output_files:
        output_files["config"] = input_file.with_name(f"{input_stem}_config{suffix}")

    # Get the implementation relative to the output path
    stub_module = _rewrite_path_as_import(
        output_files["stub"].relative_to(output_files["implementation"].parent)
    )

    spec_as_yaml = input_file.read_text()
    generated = generate_from_spec(
        spec_as_yaml,
        "yaml",
        templates=templates,
        language=language,
        modules={"stub": stub_module}
    )
    for template_type, code in generated.items():
        output_files[template_type].write_text(code)

    # Return the created files for reporting
    return output_files


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
  langgraph-gen spec.yml --stub-template py-class-stub.j2 --impl-template py-impl-stub.j2
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
        "-sO",
        "--stub-outfile",
        type=Path,
        help="Output file path for the agent stub",
        default=None,
    )

    parser.add_argument(
        "-iO",
        "--impl-output",
        type=Path,
        help="Output file path for the agent implementation",
        default=None,
    )
    
    parser.add_argument(
        "-SO",
        "--state-outfile",
        type=Path,
        help="Output file path for the agent state",
        default=None,
    )

    parser.add_argument(
        "-CO",
        "--config-outfile",
        type=Path,
        help="Output file path for the agent config",
        default=None,
    )
    
    parser.add_argument(
        "-L",
        "--list-templates",
        action="store_true",
        help="List available templates and exit",
    )
    
    parser.add_argument(
        "-sT",
        "--stub-template",
        type=str,
        help="Custom template to use for the agent stub",
        default="default",
    )
    
    parser.add_argument(
        "-iT",
        "--impl-template",
        type=str,
        help="Custom template to use for the implementation",
        default="default",
    )

    parser.add_argument(
        "-ST",
        "--state-template",
        type=str,
        help="Custom template to use for the state",
        default="default",
    )

    parser.add_argument(
        "-CT",
        "--config-template",
        type=str,
        help="Custom template to use for the config",
        default="default",
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
    if args.stub_outfile:
        output_files["stub"] = args.stub_outfile
    if args.impl_output:
        output_files["implementation"] = args.impl_output
    if args.state_outfile:
        output_files["state"] = args.state_outfile
    if args.config_outfile:
        output_files["config"] = args.config_outfile

    templates = {}
    if args.stub_template:
        templates["stub"] = args.stub_template
    if args.impl_template:
        templates["implementation"] = args.impl_template
    if args.state_template:
        templates["state"] = args.state_template
    if args.config_template:
        templates["config"] = args.config_template

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
