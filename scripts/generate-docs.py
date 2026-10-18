#!/usr/bin/env -S uv run python
# Copyright 2026 Michael Hacker
# SPDX-License-Identifier: Apache-2.0

"""Generate the Markdown pages of the Docusaurus website.

The API reference is rendered from the NumPy-style docstrings with griffe. The home, donation,
contributing and changelog pages are copied from the marked sections of the Markdown files in the
repository root, the hand-written pages from ``website/content``. All pages are written to
``website/docs``, which is not tracked by git.
"""

import re
import shutil
from pathlib import Path
from typing import ClassVar

import griffe

ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUT: Path = ROOT / "website" / "docs"
CONTENT: Path = ROOT / "website" / "content"
PACKAGE: str = "netzooe_eservice_api"
CLIENT: str = "client"
SIGNATURE_WIDTH: int = 100


class DocsGenerator:
    """Render the documentation pages into the Docusaurus docs folder."""

    _ROLE_PATTERN: re.Pattern[str] = re.compile(r":[a-z]+:`~?([^`]+)`")
    _LITERAL_PATTERN: re.Pattern[str] = re.compile(r"``([^`]+)``")

    # Links in the copied Markdown files, mapped to the generated pages, so Docusaurus checks them
    _LINKS: ClassVar[dict[str, str]] = {
        "(CHANGELOG.md)": "(changelog.md)",
        "(CONTRIBUTING.md)": "(contributing.md)",
        "(https://superbox-dev.github.io/netzooe_eservice_api/usage": "(usage.md",
        "(https://superbox-dev.github.io/netzooe_eservice_api/api": "(api.md",
    }

    def __init__(self, output: Path) -> None:
        """Initialize the generator.

        Parameters
        ----------
        output
            Folder for the generated Markdown pages, replaced on every run.

        """
        self.output: Path = output
        self.package: griffe.Object | griffe.Alias = griffe.load(
            PACKAGE,
            search_paths=[ROOT],
            docstring_parser=griffe.Parser.numpy,
        )

    def run(self) -> None:
        """Write all pages."""
        shutil.rmtree(self.output, ignore_errors=True)
        self.output.mkdir(parents=True)

        for page in sorted(CONTENT.glob("*.md")):
            shutil.copyfile(page, self.output / page.name)

        self._write_home()
        self._write_page("donation.md", self._front_matter("Donation", 90), self._extract("README.md", "donation"))
        self._write_page(
            "api.md",
            self._front_matter("API client", 10),
            self._render_client(self._get_class("api", "NetzOOEeServiceAPI")),
        )
        self._write_page("types.md", self._front_matter("Types", 20), self._render_types())
        self._write_page("constants.md", self._front_matter("Constants", 30), self._render_constants())
        self._write_page("errors.md", self._front_matter("Errors", 40), self._render_errors())
        self._write_page(
            "changelog.md",
            self._front_matter("Changelog", 70, hide_toc=True),
            "# Changelog",
            self._extract("CHANGELOG.md", ""),
        )
        self._write_page(
            "contributing.md",
            self._front_matter("Contributing", 80),
            "# Contributing",
            self._extract("CONTRIBUTING.md", "contributing"),
        )

    def _write_home(self) -> None:
        intro: str = self._extract("README.md", "home")
        self._write_page(
            "index.md",
            self._front_matter("Introduction", 0, slug="/"),
            "# Netz OÖ eService API",
            intro,
        )

    def _write_page(self, path: str, *blocks: str) -> None:
        content: str = "\n\n".join(block.strip("\n") for block in blocks if block)
        (self.output / path).write_text(f"{content}\n", encoding="utf-8")

    def _get_class(self, module: str, name: str) -> griffe.Class:
        cls: griffe.Object | griffe.Alias = self.package[module][name]

        if not isinstance(cls, griffe.Class):
            msg: str = f"{module}.{name} is not a class"
            raise TypeError(msg)

        return cls

    def _get_classes(self, module: str) -> list[griffe.Class]:
        """Return the public classes defined in a module, in source order."""
        return [
            cls
            for name, cls in self.package[module].members.items()
            if isinstance(cls, griffe.Class) and not name.startswith("_")
        ]

    @staticmethod
    def _front_matter(title: str, position: int, *, slug: str = "", hide_toc: bool = False) -> str:
        lines: list[str] = ["---", f"title: {title}", f"sidebar_position: {position}"]

        if slug:
            lines.append(f"slug: {slug}")

        if hide_toc:
            lines.append("hide_table_of_contents: true")

        lines.append("---")
        return "\n".join(lines)

    def _extract(self, filename: str, marker: str) -> str:
        """Join all sections of a Markdown file between ``<!--start-marker-->`` and ``<!--end-marker-->``."""
        suffix: str = f"-{marker}" if marker else ""
        text: str = (ROOT / filename).read_text(encoding="utf-8")
        pattern: re.Pattern[str] = re.compile(rf"<!--start{suffix}-->(.*?)<!--end{suffix}-->", re.DOTALL)
        content: str = "\n\n".join(part.strip("\n") for part in pattern.findall(text))

        if not content:
            msg: str = f"No <!--start{suffix}--> section in {filename}"
            raise ValueError(msg)

        for link, target in self._LINKS.items():
            content = content.replace(link, target)

        return content

    def _render_client(self, client: griffe.Class) -> str:
        init: griffe.Function = client.functions["__init__"]
        blocks: list[str] = [
            f"# {client.name}",
            self._code(f"from {PACKAGE} import {client.name}"),
            self._code(self._signature(client.name, init, prefix="class ")),
            self._render_text(client.docstring),
            self._render_docstring(init.docstring, skip_summary=True),
        ]

        for name, member in client.attributes.items():
            if "property" in member.labels and not name.startswith("_"):
                blocks.extend(
                    [
                        f"## {name}",
                        self._code(f"{CLIENT}.{name}: {member.annotation}"),
                        self._render_docstring(member.docstring),
                    ],
                )

        blocks.extend(self._render_functions(client))
        return "\n\n".join(block for block in blocks if block)

    def _render_types(self) -> str:
        blocks: list[str] = ["# Types", "Types for the arguments of the client methods."]

        for cls in self._get_classes("api"):
            if not any(str(base) == "TypedDict" for base in cls.bases):
                continue

            blocks.extend(
                [
                    f"## {cls.name}",
                    self._code(f"from {PACKAGE} import {cls.name}"),
                    self._render_text(cls.docstring),
                    self._render_keys(cls),
                ],
            )

        return "\n\n".join(block for block in blocks if block)

    def _render_keys(self, cls: griffe.Class) -> str:
        """Render the keys of a ``TypedDict`` as a table, with the descriptions of its ``Attributes`` section."""
        descriptions: dict[str, str] = {}

        for section in cls.docstring.parsed if cls.docstring else []:
            if isinstance(section, griffe.DocstringSectionAttributes):
                descriptions.update(
                    (item.name, self._convert(item.description).replace("\n", " ")) for item in section.value
                )

        # A pipe in a type like `str | None` would end the table cell
        lines: list[str] = ["| Key | Type | Description |", "|---|---|---|"]
        lines.extend(
            f"| `{name}` | `{str(attribute.annotation).replace('|', r'\|')}` | {descriptions.get(name, '')} |"
            for name, attribute in cls.attributes.items()
        )
        return "\n".join(lines)

    def _render_constants(self) -> str:
        module: griffe.Object | griffe.Alias = self.package["constants"]
        constants: list[str] = [
            f"{name}: {attribute.annotation} = {attribute.value}"
            for name, attribute in module.attributes.items()
            if "module-attribute" in attribute.labels and not name.startswith("_")
        ]
        blocks: list[str] = [
            "# Constants",
            self._render_text(module.docstring),
            "## Portal",
            self._code("\n".join(constants)),
            "## Enums",
            (
                "The values are the exact strings the eService portal expects. Enum parameters of the client methods "
                "accept a member, a list of members or `None`."
            ),
        ]

        for cls in self._get_classes("constants"):
            members: list[str] = ["| Member | Value |", "|---|---|"]
            members.extend(
                f"| `{name}` | `{attribute.value}` |"
                for name, attribute in cls.attributes.items()
                if not name.startswith("_")
            )
            blocks.extend(
                [
                    f"### {cls.name}",
                    self._code(f"from {PACKAGE} import {cls.name}"),
                    self._render_text(cls.docstring),
                    "\n".join(members),
                ],
            )

        return "\n\n".join(block for block in blocks if block)

    def _render_errors(self) -> str:
        blocks: list[str] = ["# Errors", "All exceptions of the client are subclasses of `APIError`."]

        for cls in self._get_classes("error"):
            bases: str = ", ".join(str(base) for base in cls.bases)
            blocks.extend(
                [
                    f"## {cls.name}",
                    self._code(f"from {PACKAGE} import {cls.name}"),
                    self._code(f"class {cls.name}({bases})"),
                    self._render_text(cls.docstring),
                ],
            )

            if "__init__" in cls.members and not cls.members["__init__"].inherited:
                init: griffe.Function = cls.functions["__init__"]
                blocks.extend(
                    [
                        self._code(self._signature(cls.name, init, prefix="")),
                        self._render_docstring(init.docstring, skip_summary=True),
                        self._render_attributes(cls),
                    ],
                )

        return "\n\n".join(block for block in blocks if block)

    @staticmethod
    def _render_attributes(error: griffe.Class) -> str:
        lines: list[str] = ["**Attributes**", ""]
        lines.extend(
            f"- **{name}** `{attribute.annotation}`"
            for name, attribute in error.attributes.items()
            if not name.startswith("_")
        )
        return "\n".join(lines)

    def _render_functions(self, cls: griffe.Class) -> list[str]:
        blocks: list[str] = []

        for name, function in cls.functions.items():
            if name.startswith("_"):
                continue

            prefix: str = "async def " if "async" in function.labels else "def "
            blocks.extend(
                [
                    f"## {name}",
                    self._code(self._signature(name, function, prefix=prefix)),
                    self._render_docstring(function.docstring),
                ],
            )

        return blocks

    def _signature(self, name: str, function: griffe.Function, *, prefix: str) -> str:
        parameters: list[str] = []
        keyword_only: bool = False
        positional_only: bool = False

        for parameter in function.parameters:
            if parameter.name in {"self", "cls"}:
                continue

            if parameter.kind is griffe.ParameterKind.positional_only:
                positional_only = True
            elif positional_only:
                parameters.append("/")
                positional_only = False

            if parameter.kind is griffe.ParameterKind.var_positional:
                keyword_only = True
            elif parameter.kind is griffe.ParameterKind.keyword_only and not keyword_only:
                parameters.append("*")
                keyword_only = True

            parameters.append(self._parameter(parameter))

        if positional_only:
            parameters.append("/")

        # A class signature is rendered from its __init__ without the return annotation
        returns: str = "" if prefix in {"class ", ""} else f" -> {function.returns}"
        line: str = f"{prefix}{name}({', '.join(parameters)}){returns}"

        if len(line) <= SIGNATURE_WIDTH or not parameters:
            return line

        lines: str = "".join(f"    {parameter},\n" for parameter in parameters)
        return f"{prefix}{name}(\n{lines}){returns}"

    @staticmethod
    def _parameter(parameter: griffe.Parameter) -> str:
        stars: str = {
            griffe.ParameterKind.var_positional: "*",
            griffe.ParameterKind.var_keyword: "**",
        }.get(parameter.kind, "")
        text: str = f"{stars}{parameter.name}"

        if parameter.annotation is not None:
            text = f"{text}: {parameter.annotation}"

        if parameter.default is not None:
            text = f"{text} = {parameter.default}"

        return text

    def _render_text(self, docstring: griffe.Docstring | None) -> str:
        if docstring is None:
            return ""

        return "\n\n".join(
            self._convert(section.value)
            for section in docstring.parsed
            if section.kind is griffe.DocstringSectionKind.text
        )

    def _render_docstring(self, docstring: griffe.Docstring | None, *, skip_summary: bool = False) -> str:
        if docstring is None:
            return ""

        blocks: list[str] = []

        for section in docstring.parsed:
            if isinstance(section, griffe.DocstringSectionText):
                text: str = section.value

                # The summary of __init__ ("Initialize the ...") repeats the class docstring
                if skip_summary:
                    text = text.split("\n\n", maxsplit=1)[1] if "\n\n" in text else ""
                    skip_summary = False

                blocks.append(self._convert(text))
            elif isinstance(section, griffe.DocstringSectionParameters):
                blocks.append(self._render_items("Parameters", section.value))
            elif isinstance(section, griffe.DocstringSectionReturns):
                blocks.append(self._render_items("Returns", section.value))
            elif isinstance(section, griffe.DocstringSectionRaises):
                blocks.append(self._render_items("Raises", section.value))
            elif isinstance(section, griffe.DocstringSectionExamples):
                blocks.extend(self._render_examples(section))

        return "\n\n".join(block for block in blocks if block)

    def _render_items(
        self,
        title: str,
        items: list[griffe.DocstringParameter] | list[griffe.DocstringReturn] | list[griffe.DocstringRaise],
    ) -> str:
        lines: list[str] = [f"**{title}**", ""]

        for item in items:
            parts: list[str] = []

            if isinstance(item, griffe.DocstringParameter):
                parts.append(f"**{item.name}**")

            if item.annotation is not None:
                parts.append(f"`{item.annotation}`")

            if isinstance(item, griffe.DocstringParameter) and item.default is not None:
                parts.append(f"(default: `{item.default}`)")

            description: str = self._convert(item.description).replace("\n", " ")
            lines.append(f"- {' '.join(parts)}" + (f": {description}" if description else ""))

        return "\n".join(lines)

    def _render_examples(self, section: griffe.DocstringSectionExamples) -> list[str]:
        blocks: list[str] = ["**Example**"]

        for kind, text in section.value:
            if kind is griffe.DocstringSectionKind.examples:
                code: str = "\n".join(re.sub(r"^(>>>|\.\.\.) ?", "", line) for line in text.splitlines())
                blocks.append(self._code(code))
            else:
                blocks.append(self._convert(text))

        return blocks

    def _convert(self, text: str) -> str:
        """Convert reStructuredText markup of a docstring to Markdown."""
        text = self._ROLE_PATTERN.sub(r"`\1`", text)
        return self._LITERAL_PATTERN.sub(r"`\1`", text)

    @staticmethod
    def _code(code: str) -> str:
        return f"```python\n{code}\n```"


if __name__ == "__main__":
    DocsGenerator(OUTPUT).run()
