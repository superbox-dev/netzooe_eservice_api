# Website

- Never edit `website/docs/`, `scripts/generate-docs.py` generates it:
  - API reference from the docstrings (griffe): client, types (`TypedDict`s in `api.py`), constants and enums, errors
  - home, donation, contributing and changelog from the markers in `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md`
  - hand-written pages from `website/content/`
- Pages in `website/content/`: `sidebar_position` but no `title` in the front matter, the title comes from the `#`
  heading
- `website/content/usage.md` sections: read data, session, project-specific sections, errors
- Examples only with test data or placeholders, never real credentials, serial numbers or meter point numbers
- Preview image for shared links: `website/static/img/social-card.png` (1200 × 630, same layout in all projects)
- The navbar links to the website of the Home Assistant integration (`Integration`)
- Design after home-assistant.io:
  - `website/src/css/custom.css` and the wrapped `website/src/theme/TOC/`
  - light mode by default, the right column at least `17.5rem` wide on smaller screens
  - the project card in `website/src/components/ProjectInfo/` shows the brand logo of the integration
    (`website/static/logo.png`, `dark_logo.png`), like the integration card
