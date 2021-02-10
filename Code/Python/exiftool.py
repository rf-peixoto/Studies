from exiftool import ExifTool

files = ["the-web-application-hackers-handbook.pdf", "Mastering Malware Analysis.pdf"]

with ExifTool as et:
    metadata = et.get_metadata_batch(files)
for data in metadata:
    print("{:20.20} {:20.20}".format(data["SourceFile"], data["EXIF:DateTimeOriginal"]))

