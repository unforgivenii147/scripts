import pdfkit

pdfkit.from_url(url, "output.pdf", options={"enable-local-file-access": None})
# Can also convert PDF to PNG with ImageMagick
