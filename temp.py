from settings import check_blank_attach, ls_cmd

a = ls_cmd('')
subject = "Insured Name : SIEGWERK INDIA PRIVATE LTD Policy No : OG-21-1113-8403-00000103 ID Card No : GMC-21111330103-E669D Ptn Name : AMIYA KUMAR MUKHERJEE Claim ID : 4501162 Cashless Claim Covering Letter"
date = "02/03/2021 19:09:02"
id = "AAMkAGMxMzcwMjVlLThjYjYtNGJlOC1iOWQzLTUzZjg5MTEwOTJiZABGAAAAAABg8S9egpbpQom_SYSQFJTABwA80npqDluGRIdxtgeTfSBNAAAAAAEMAAA80npqDluGRIdxtgeTfSBNAALHEjwQAAA="
a = check_blank_attach(subject=subject, date=date, id=id)
pass