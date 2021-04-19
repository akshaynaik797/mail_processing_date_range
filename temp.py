import pdfkit

from settings import pdfconfig
data = "ils_ho/new_attach/1.txt"
dst = 'ils_ho/new_attach/22967570_.pdf'
pdfkit.from_file(data, dst, configuration=pdfconfig)