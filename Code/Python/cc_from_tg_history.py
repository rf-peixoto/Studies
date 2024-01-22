import os
import re

# Define the regular expression pattern to extract the desired data
pattern = r'(\d+\|\d+\|\d+\|\d+)'

# Specify the directory containing your HTML files
directory_path = r'C:\path\to\your\html\files'  # Use a raw string with r-prefix

# Initialize a list to store the extracted data
extracted_data = []

# Iterate through the files in the directory
print('Extracting data.')
encodings = ['ascii','big5','big5hkscs','cp037','cp273','cp424','cp437','cp500','cp720','cp737','cp775','cp850','cp852','cp855','cp856','cp857','cp858','cp860','cp861','cp862','cp863','cp864','cp865','cp866','cp869','cp874','cp875','cp932','cp949','cp950','cp1006','cp1026','cp1125','cp1140','cp1250','cp1251','cp1252','cp1253','cp1254','cp1255','cp1256','cp1257','cp1258','euc_jp','euc_jis_2004','euc_jisx0213','euc_kr','gb2312','gbk','gb18030','hz','iso2022_jp','iso2022_jp_1','iso2022_jp_2','iso2022_jp_2004','iso2022_jp_3','iso2022_jp_ext','iso2022_kr','latin_1','iso8859_2','iso8859_3','iso8859_4','iso8859_5','iso8859_6','iso8859_7','iso8859_8','iso8859_9','iso8859_10','iso8859_11','iso8859_13','iso8859_14','iso8859_15','iso8859_16','johab','koi8_r','koi8_t','koi8_u','kz1048','mac_cyrillic','mac_greek','mac_iceland','mac_latin2','mac_roman','mac_turkish','ptcp154','shift_jis','shift_jis_2004','shift_jisx0213','utf_32','utf_32_be','utf_32_le','utf_16','utf_16_be','utf_16_le','utf_7','utf_8','utf_8_sig']
for en in encodings:
    print('Trying {0}'.format(en))
    try:
        for filename in os.listdir(directory_path):
            if filename.endswith(".html"):
                # Construct the full path to the HTML file
                file_path = os.path.join(directory_path, filename)

                # Open and read the HTML file
                #with open(file_path, 'r', encoding='utf-8') as file:
                #with open(file_path, 'r', encoding='ISO-8859-6') as file:
                with open(file_path, 'r', encoding=en) as file:
                    html_content = file.read()

                # Use regex to find all matches in the HTML content
                matches = re.findall(pattern, html_content)

                # Add the matches to the extracted_data list
                extracted_data.extend(matches)
        #break # This one may cause a loop even when one of the encodings was enough.
    except Exception as error:# UnicodeDecodeError:
        print(error)
        continue
            

# Export the extracted data
with open('extracted.txt', 'w') as fl:
    for data in extracted_data:
        fl.write(data + '\n')
print('Done')
