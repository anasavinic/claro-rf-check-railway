FROM squidfunk/mkdocs-material

RUN pip install mkdocstrings[python]
RUN pip install mkdocs-glightbox

WORKDIR /docs
CMD ["serve", "-f", "mkdocs.yml", "-a", "0.0.0.0:8000", "--dirtyreload"]