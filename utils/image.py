from utils.useful import run_async

from PIL import Image, ImageFont, UnidentifiedImageError
from wand.image import Image as WImage
from wand.color import Color as WColor
from wand.font import Font as WFont
from pilmoji import Pilmoji
import textwrap
import emoji
import numpy
import cv2

from subprocess import Popen, PIPE
from typing import Union
from shlex import split
from io import BytesIO

class EditImage:
    def __init__(self, file: BytesIO):
        self.image = Image.open(file).convert("RGBA")

    def _save(self, img_format: str = "PNG", quality: int = 95):
        """General function for saving images as byte objects"""
        # save the image as bytes
        img_byte_arr = BytesIO()
        self.image.save(img_byte_arr, img_format, quality = quality)
        result = BytesIO(img_byte_arr.getvalue())

        return result

    @run_async
    def resize_even(self):
        """Resizes the image so that its width and height are even"""
        width, height = self.image.size

        # add 1 to the width or height if it's odd
        # this is necessary for when ffmpeg uses it later on to make an mp4 file
        if width % 2 != 0: width += 1
        if height % 2 != 0: height += 1

        self.image = self.image.resize((width, height))

        # adds a black background to the image if it's transparent
        background = Image.new("RGBA", (width, height), (0, 0, 0))
        self.image = Image.alpha_composite(background, self.image)

        result = self._save()
        return result

    @run_async
    def jpeg(self):
        """Returns a low quality version of the image"""
        file_rgba = self.image.convert("RGBA")

        # shrink the image to 80% of it's original size
        orig_w, orig_h = file_rgba.size
        small_w = round(0.8 * orig_w)
        small_h = round(0.8 * orig_h)
        small = (small_w, small_h)
        file_rgba = file_rgba.resize(small)

        # create a black background behind the image (useful if it's a transparent png)
        background = Image.new("RGBA", small, (0, 0, 0))
        alpha_composite = Image.alpha_composite(background, file_rgba)
        self.image = alpha_composite.convert("RGB")  # converting to RGB for jpeg output

        result = self._save("JPEG", 4)
        return result

    @run_async
    def resize(self, size: tuple):
        """Resizes the image to a given size"""
        self.image = self.image.resize(size)

        result = self._save()
        return result

    @run_async
    def caption(self, caption: Image.Image):
        """Adds a caption onto the image"""
        width, height = self.image.size

        # create a new image that contains both the caption and the original image
        new_img = Image.new("RGBA", (width, height + caption.height))

        new_img.paste(caption, (0,0))
        new_img.paste(self.image, (0, caption.height))

        self.image = new_img

        result = self._save()
        return result

    @run_async
    def uncaption(self):
        """Removes captions from the image"""
        bounds = get_content_bounds(self.image)

        self.image = self.image.crop(bounds)

        result = self._save()
        return result

class EditGif:
    def __init__(self, gif: BytesIO):
        self.b = gif
        self.gif = Image.open(gif)
        self.mode = self._analyse()
        self.last_frame = self.gif.convert("RGBA")
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def _analyse(self):
        """Determines if the gif's mode is full (changes whole frame) or partial (changes parts of the frame)"""
        # taken from https://gist.github.com/rockkoca/30357703f42f9d17c6fa121cf4dd1d8e
        try:
            while True:
                # check update region dimensions
                if self.gif.tile and self.gif.tile[0][1][2:] != self.gif.size:
                    return "partial"

                # move to next frame
                self.gif.seek(self.gif.tell() + 1)
        except EOFError:
            pass

        return "full"

    def _next_frame(self):
        """Seeks to the next frame in the gif"""
        self.gif.seek(self.i)
        self.new_frame = Image.new("RGBA", self.gif.size)

        if self.mode == "partial":
            self.new_frame.paste(self.last_frame)

        self.new_frame.paste(self.gif, (0,0), self.gif.convert("RGBA"))

    def _append_frame(self, image: Image.Image):
        """Appends the given frame to a list (along with its duration"""
        self.frames.append(image)
        self.durations.append(self.gif.info["duration"])
        self.last_frame = self.new_frame

    def _save(self):
        """Converts the saved images into a gif byte object"""
        # --nextfile: read from bytes, -O: optimize, +x -w: remove gif extensions and warnings
        cmd = "gifsicle --nextfile -O +x -w "

        # generate delay information
        for duration in self.durations:
            cmd += f"-d{duration // 10} - "

        # loop forever and read output as bytes
        cmd += "--loopcount=0 --dither -o -"

        p = Popen(split(cmd), stdin = PIPE, stdout = PIPE)

        # send frames to gifsicle
        for frame in self.frames:
            b = BytesIO()
            frame.save(b, format = "GIF")

            p.stdin.write(b.getvalue())

        p.stdin.close()
        result = p.stdout.read()

        return BytesIO(result)

    @run_async
    def resize(self, new_size: tuple[int]):
        """Resizes the gif to a given size"""
        for self.i in range(self.gif.n_frames):
            self._next_frame()

            # resize frame
            resized_frame = self.new_frame.resize(new_size)

            self._append_frame(resized_frame)

        result = self._save()
        return result

    @run_async
    def caption(self, text: Image.Image):
        """Captions the gif using a caption image"""
        for self.i in range(self.gif.n_frames):
            self._next_frame()

            # create image that will contain both caption and original frame
            captioned_frame = Image.new("RGBA", (self.new_frame.width, self.new_frame.height + text.height))

            # add caption and then original frame under it
            captioned_frame.paste(text, (0, 0))
            captioned_frame.paste(self.new_frame, (0, text.height))

            self._append_frame(captioned_frame)

        result = self._save()
        return result

    @run_async
    def uncaption(self):
        """Removes captions from the gif"""
        for self.i in range(self.gif.n_frames):
            self._next_frame()

            if self.i == 0:
                bounds = get_content_bounds(self.new_frame)

            if not bounds:
                return

            cropped_frame = self.new_frame.crop(bounds)

            self._append_frame(cropped_frame)

        result = self._save()
        return result

@run_async
def get_image_size(file: BytesIO):
    """Gets the dimensions of an image/gif"""
    try:
        return Image.open(file).size
    except UnidentifiedImageError:
        return

@run_async
def create_caption_text(text: str, width: int):
    """Creates the caption image (white background with black text)"""
    spacing = width // 40
    font_size = width // 10
    font_path = "fonts/futura.ttf"

    # replace ellipsis characters and remove extra whitespace
    text = text.replace("…", "...")
    text = " ".join(text.split())

    # wrap caption text
    caption_lines = textwrap.wrap(text, 21)
    caption = "\n".join(caption_lines)

    font = ImageFont.truetype(font_path, font_size)

    # get the size of the rendered text
    text_height = (font.getsize_multiline(caption, spacing = spacing)[1] + font_size)

    # get all emojis in text
    emojis = emoji.distinct_emoji_list(caption)

    if emojis:
        # create a blank image using the given width and the text height
        caption_img = Image.new("RGB", (width, text_height), (255, 255, 255))
        x, _ = caption_img.width // 2, caption_img.height // 2

        with Pilmoji(caption_img) as pilmoji:
            line_sizes = [pilmoji.getsize(line, font, spacing = spacing, emoji_scale_factor = 1.25) for line in caption_lines]

            for i, (line, size) in enumerate(zip(caption_lines, line_sizes)):
                # align text line to the center horizontally (x) and from the top downwards (y)
                x_offset = x + (size[0] // -2)
                y_offset = (round(size[1] / 2.5) + ((size[1] + spacing) * i))

                pilmoji.text((x_offset, y_offset), line, (0, 0, 0), font, spacing = spacing, emoji_scale_factor = 1.25)
    else:
        with WImage(width = width, height = text_height, background = WColor("#fff")) as img:
            img.font = WFont(font_path, font_size)
            img.caption(caption, gravity = "center")

            caption_img = Image.open(BytesIO(img.make_blob("png")))

    return caption_img

def get_content_bounds(img: Union[Image.Image, cv2.Mat]):
    """
    Gets the size of the main part of an image (without the border/caption),
    mostly using code from [here](https://stackoverflow.com/a/64796067)
    """

    # convert PIL image to cv2 image
    if isinstance(img, Image.Image):
        img = cv2.cvtColor(numpy.array(img), cv2.COLOR_RGB2BGR)

    # invert the image and convert it to grayscale
    img_invert = cv2.bitwise_not(img)
    img_gray = cv2.cvtColor(img_invert, cv2.COLOR_BGR2GRAY)

    # create the threshold for contours
    thresh = cv2.threshold(img_gray, 20, 255, cv2.THRESH_BINARY)[1]

    # apply open morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # get bounding box coordinates from largest external contour
    contours = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    big_contour = max(contours, key = cv2.contourArea)
    _, y, _, _ = cv2.boundingRect(big_contour)

    bounds = 0, y, img.shape[1], img.shape[0]

    return bounds