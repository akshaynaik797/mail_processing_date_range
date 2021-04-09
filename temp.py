import re

import pdfkit
import weasyprint

from settings import pdfconfig

html_file = '/home/akshay/Downloads/temp.html'
pdf_file = '/home/akshay/Downloads/1.pdf'

def remove_img_tags(data):
    p = re.compile(r'<img.*?/>')
    return p.sub('', data)

if __name__ == '__main__':
    with open(html_file, 'r') as fp:
        data = fp.read()
    data = remove_img_tags(data)
    pdfkit.from_string(data, pdf_file, configuration=pdfconfig)


