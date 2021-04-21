from exif import Image

class ExifAPI:
    def __init__(self):
        pass

    def open(self, image):
        try:
            with open(image, "rb") as fl:
                tmp = Image(fl)
            if tmp.has_exif:
                print("Exif version {0}.".format(tmp.exif_version))
            return tmp
        except Exception as error:
            print(error)
