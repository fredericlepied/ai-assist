# ai-assist Presentation

LaTeX Beamer slide deck presenting the ai-assist project to engineering teams.

## Requirements

A TeX Live installation with the following packages:

- `texlive-base` (pdflatex)
- `texlive-beamer`
- `texlive-beamertheme-metropolis`
- `texlive-pgf` (TikZ)
- `texlive-fira` (Fira Sans/Mono fonts, required by metropolis)
- `texlive-ec` (EC fonts for T1 encoding)
- `texlive-grfext`
- `texlive-booktabs`
- `texlive-listings`
- `texlive-appendixnumberbeamer`
- `texlive-cm-super`

### Fedora / RHEL

```bash
sudo dnf install \
  texlive-base texlive-beamer texlive-beamertheme-metropolis \
  texlive-pgf texlive-fira texlive-ec texlive-grfext \
  texlive-booktabs texlive-listings texlive-appendixnumberbeamer \
  texlive-cm-super
```

## Building

```bash
make
```

The PDF is generated as `ai-assist-presentation.pdf`.

To clean generated files:

```bash
make clean
```
