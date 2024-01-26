import io
import base64

import requests
from PIL import Image, ImageDraw, ImageFont
from PIL.Image import Image as ImageType

from utils.vars import FONTS_PATH

SPOTIFY_FONT = f'{FONTS_PATH}/GothamMedium.ttf'


def get_image_from_url(img_url: str | None):
  if img_url:
    img_bytes = requests.get(img_url).content
    return Image.open(io.BytesIO(img_bytes))
  return Image.new('RGB', (500, 500), (0, 0, 0))

def format_collection_cover(img_url: str | None, text_key: str, text_mode: str):
  img = get_image_from_url(img_url)

  black = Image.new('RGB', img.size, (0, 0, 0))
  mask = Image.new('RGBA', img.size, (0, 0, 0, 42))

  img_edited = Image.composite(img, black, mask)

  draw = ImageDraw.Draw(img_edited)

  fillH1 = (255, 255, 255)
  fontH1 = ImageFont.truetype(SPOTIFY_FONT, int(img_edited.width * 0.50))
  _, _, fontWidthA, fontHeightA = draw.textbbox((0, 0), text_key, font=fontH1)

  fillH4 = (177, 179, 181)
  fontH4 = ImageFont.truetype(SPOTIFY_FONT, int(img_edited.width * 0.13))
  _, _, fontWidthB, fontHeightB = draw.textbbox((0, 0), text_mode, font=fontH4)

  xyH1 = ((img_edited.width-fontWidthA)/2, (img_edited.height-fontHeightA)/2 - fontHeightB)
  xyH4 = ((img_edited.width-fontWidthB)/2, (img_edited.height-fontHeightB)/2 + fontHeightA/1.5)

  draw.text(xyH1, text=text_key, fill=fillH1, font=fontH1)
  draw.text(xyH4, text=text_mode, fill=fillH4, font=fontH4)

  return img_edited

def base64_encode_image(image: ImageType) -> bytes:  
  buffered = io.BytesIO()
  image.save(buffered, format='JPEG')
  img_bytes = base64.b64encode(buffered.getvalue())
  return img_bytes

def get_encoded_cover(*, img_url: str | None, text_key: str, text_mode: str) -> bytes:
  img = format_collection_cover(img_url, text_key, text_mode)
  base64_img = base64_encode_image(img)
  return base64_img
