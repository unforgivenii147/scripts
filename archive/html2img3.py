from weasyprint import HTML

HTML(url).write_png("output.png")
# or from local HTML file
HTML("index.html").write_png("output.png")
