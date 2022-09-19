from captcha.image import ImageCaptcha

# Image size:
img = ImageCaptcha(width = 300, height = 100)
text = input("Text: ")

data = img.generate(text)

img.write(text, "output.png")
