TEX = pdflatex
FLAGS = -interaction=nonstopmode
SRC = ai-assist-presentation.tex
PDF = $(SRC:.tex=.pdf)

.PHONY: all clean

all: $(PDF)

$(PDF): $(SRC)
	$(TEX) $(FLAGS) $(SRC)
	$(TEX) $(FLAGS) $(SRC)

clean:
	rm -f *.aux *.log *.nav *.out *.snm *.toc *.vrb *.pdf missfont.log
