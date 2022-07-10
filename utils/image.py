from PIL import Image, ImageFont, ImageDraw
from subprocess import Popen, PIPE
from pilmoji import Pilmoji
from shlex import split
from io import BytesIO
import textwrap
import emoji

def get_size(file: BytesIO):
    """Returns the size of a file"""
    image = Image.open(file)
    size = image.width, image.height
    
    return size

def size_check(file: BytesIO):
    """Resizes a file so that it's width and height are even"""
    image = Image.open(file).convert('RGBA')
    width, height = image.size

    # add 1 to the width or height if it's odd
    # this is necessary for when ffmpeg uses it later on to make an mp4 file
    if width % 2 != 0: width += 1
    if height % 2 != 0: height += 1

    image = image.resize((width, height))

    # adds a black background to the image if it's transparent
    background = Image.new('RGBA', (width, height), (0, 0, 0))
    alpha_composite = Image.alpha_composite(background, image)

    # save the new image as bytes
    img_byte_arr = BytesIO()
    alpha_composite.save(img_byte_arr, format = 'PNG')
    result = BytesIO(img_byte_arr.getvalue())

    return result

def jpeg(file: BytesIO):
    """Returns a low quality version of the file"""
    file_rgba = Image.open(file).convert('RGBA')

    # shrink the image to 80% of it's original size
    orig_w, orig_h = file_rgba.size
    small_w = round(0.8 * orig_w)
    small_h = round(0.8 * orig_h)
    small = (small_w, small_h)
    file_rgba = file_rgba.resize(small)

    # create a black background behind the image (useful if it's a transparent png)
    background = Image.new('RGBA', small, (0, 0, 0))
    alpha_composite = Image.alpha_composite(background, file_rgba)
    file_rgb = alpha_composite.convert('RGB') # converting to RGB for jpeg output

    # save the image as a bytes object
    img_byte_arr = BytesIO()
    file_rgb.save(img_byte_arr, format = 'JPEG', quality = 4) # "quality = 4" lowers the quality
    result = BytesIO(img_byte_arr.getvalue())

    return result

def resize(file: BytesIO, size: tuple[int, int]):
    """Resizes a file to a given size"""
    file: Image.Image = Image.open(file)
    file = file.resize(size)

    img_byte_arr = BytesIO()
    file.save(img_byte_arr, format = 'PNG')
    result = BytesIO(img_byte_arr.getvalue())

    return result

def create_caption(text: str, width: int):
    """Creates the caption image (white background with black text)"""
    spacing = width // 40
    font_size = width // 10
    white = (255, 255, 255)
    
    # wrap caption text
    caption_lines = textwrap.wrap(text, width // 24, break_long_words=True)
    caption = '\n'.join(caption_lines)

    font_path = 'fonts/futura.ttf'
    font = ImageFont.truetype(font_path, font_size)

    emojis = [char for char in caption if char in emoji.UNICODE_EMOJI_ENGLISH.keys()]

    # get the size of the rendered text
    if emojis:
        with Pilmoji(Image.new('RGB', (1, 1))) as pilmoji:
            text_size = pilmoji.getsize(caption, font, spacing = spacing, emoji_scale_factor = 1.25)
    else:
        text_size = font.getsize_multiline(caption, spacing = spacing)

    # create a blank image using the given width and the text height
    caption_img = Image.new('RGB', (width, text_size[1] + font_size), white)
    x, y = caption_img.width // 2, caption_img.height // 2

    # add the text
    if emojis:
        with Pilmoji(caption_img) as pilmoji:
            x_offset, y_offset = (text_size[0] // -2, text_size[1] // -2)
            pilmoji.text((x + x_offset, y + y_offset), caption, (0, 0, 0), font, spacing = spacing, emoji_scale_factor = 1.25)
    else:
        ImageDraw.Draw(caption_img).text((x, y), caption, (0, 0, 0), font, 'mm', spacing, 'center')

    return caption_img

def add_caption(file: BytesIO, caption: Image.Image):
    """Adds a caption onto a given file"""
    file: Image.Image = Image.open(file)
    
    # create a new image that contains both the caption and the original image
    new_img = Image.new('RGBA', (file.width, file.height + caption.height))
    new_img.paste(caption, (0,0))
    new_img.paste(file, (0, caption.height))

    # save the result
    img_byte_arr = BytesIO()
    new_img.save(img_byte_arr, format = 'PNG')
    result = BytesIO(img_byte_arr.getvalue())

    return result

class EditGif:
    def __init__(self, gif: BytesIO):
        self.gif = Image.open(gif)
        self.mode = self._analyse()
        self.last_frame = self.gif.convert('RGBA')
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def _analyse(self):
        # determine if the gif's mode is full (changes whole frame) or partial (changes parts of the frame)
        # taken from https://gist.github.com/rockkoca/30357703f42f9d17c6fa121cf4dd1d8e
        try:
            while True:
                # check update region dimensions
                if self.gif.tile and self.gif.tile[0][1][2:] != self.gif.size:
                    return 'partial'

                # move to next frame    
                self.gif.seek(self.gif.tell() + 1)
        except EOFError:
            pass

        return 'full'
    
    def _paste(self):
        self.gif.seek(self.i)
        self.new_frame = Image.new('RGBA', self.gif.size)
        
        if self.mode == 'partial':
            self.new_frame.paste(self.last_frame)
        
        self.new_frame.paste(self.gif, (0,0), self.gif.convert('RGBA'))

    def _append(self, image: Image.Image):
        self.frames.append(image)
        self.durations.append(self.gif.info['duration'])
        self.last_frame = self.new_frame

    def resize(self, new_size: tuple[int]):
        for self.i in range(self.gif.n_frames):
            self._paste()

            # resize frame
            self.new_frame = self.new_frame.resize(new_size)

            self._append(self.new_frame)

        result = BytesIO()

        # save gif with frame and delay information
        self.frames[0].save(
            result,
            format = 'GIF', 
            save_all = True, 
            append_images = self.frames[1:], 
            duration = self.durations,
            optimize = True,
            loop = 0
        )

        return BytesIO(result.getvalue()) # IDK

    def caption(self, text: Image.Image):
        for self.i in range(self.gif.n_frames):
            self._paste()

            # create image that will contain both caption and original frame
            captioned_img = Image.new('RGBA', (self.new_frame.width, self.new_frame.height + text.height))

            # add caption and then original frame under it
            captioned_img.paste(text, (0, 0))
            captioned_img.paste(self.new_frame, (0, text.height))

            self._append(captioned_img)

        # --nextfile: read from bytes, -O: optimize, +x -w: remove gif extensions and warnings
        cmd = "gifsicle --nextfile -O +x -w "
        
        # generate delay information
        for duration in self.durations:
            cmd += f"-d{duration // 10} - "

        # loop forever and read output as bytes
        cmd += f"--loopcount=0 -o -"

        p = Popen(split(cmd), stdin = PIPE, stdout = PIPE)
        
        # send frames to gifsicle
        for frame in self.frames:
            b = BytesIO()
            frame.save(b, format = "GIF")

            p.stdin.write(b.getvalue())
        
        p.stdin.close()
        result = p.stdout.read()

        return BytesIO(result)