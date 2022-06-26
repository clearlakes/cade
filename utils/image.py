from tempfile import TemporaryDirectory, NamedTemporaryFile as create_temp
from PIL import Image, ImageFont, ImageDraw
from pilmoji import Pilmoji
import subprocess
import textwrap
import emoji
import io

def get_size(file: io.BytesIO):
    """Returns the size of a file"""
    image = Image.open(file)
    size = image.width, image.height
    
    return size

def size_check(file: io.BytesIO):
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
    img_byte_arr = io.BytesIO()
    alpha_composite.save(img_byte_arr, format = 'PNG')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def gif(file: io.BytesIO, edit_type: int, size: tuple = None, caption: Image.Image = None):
    """Function for editing gifs (and either resize or caption them)"""
    file = Image.open(file)
    
    def _analyse(file: Image.Image):
        # determine if the gif's mode is full (changes whole frame) or additive (changes parts of the frame)
        # taken from https://gist.github.com/rockkoca/30357703f42f9d17c6fa121cf4dd1d8e
        results = {'size': file.size, 'mode': 'full'}

        try:
            while True:
                # check update region dimensions
                if file.tile and file.tile[0][1][2:] != file.size:
                    results['mode'] = 'partial'
                    break

                # move to next frame    
                file.seek(file.tell() + 1)
        except EOFError:
            pass

        return results
    
    analyse = _analyse(file)

    i = 0
    last_frame = file.convert('RGBA')

    frames = []
    durations = []

    try:
        # loop over frames in the gif
        while True:
            new_frame = Image.new('RGBA', file.size)
            
            if analyse['mode'] == 'partial':
                new_frame.paste(last_frame)
            
            new_frame.paste(file, (0,0), file.convert('RGBA'))

            # if the frame is to be resized
            if edit_type == 1:
                new_frame = new_frame.resize(size)
                frames.append(new_frame)

            # if the frame is to be captioned
            if edit_type == 2:
                final_caption = Image.new('RGBA', (new_frame.width, new_frame.height + caption.height))

                final_caption.paste(caption, (0, 0))
                final_caption.paste(new_frame, (0, caption.height))

                frames.append(final_caption)

            # add the frame's duration to a list
            durations.append(file.info["duration"])

            i += 1
            last_frame = new_frame
            file.seek(i)
    except EOFError:
        pass

    if edit_type == 2:
        with TemporaryDirectory() as dir:
            files = []
            for i, frame in enumerate(frames):
                temp_path = f"{dir}/{i}.png"
                frame.save(temp_path)
                files.append(temp_path)
            
            with create_temp(suffix = ".gif") as temp:
                cmd = ["./convert"] + [opt for d, f in zip(durations, files) for opt in ("-delay", f"{d // 10}", f)] + ["-loop", "0", "-dispose", "background", "-layers", "optimize", temp.name]

                subprocess.Popen(cmd).wait()
                return io.BytesIO(temp.read())

    img_byte_arr = io.BytesIO()

    # create a new gif using the lists of created frames and their durations
    frames[0].save(
        img_byte_arr, 
        format = 'gif',
        save_all = True, 
        append_images = frames[1:], 
        duration = durations,
        optimize = True,
        loop = 0
    )

    # get the gif's data in bytes
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def jpeg(file: io.BytesIO):
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
    img_byte_arr = io.BytesIO()
    file_rgb.save(img_byte_arr, format = 'JPEG', quality = 4) # "quality = 4" lowers the quality
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def resize(file: io.BytesIO, size: tuple[int, int]):
    """Resizes a file to a given size"""
    file: Image.Image = Image.open(file)
    file = file.resize(size)

    img_byte_arr = io.BytesIO()
    file.save(img_byte_arr, format = 'png')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def create_caption(text: str, width: int):
    """Creates the caption image (white background with black text)"""
    spacing = width // 40
    font_size = width // 10
    white = (255, 255, 255)
    
    # wrap caption text
    caption_lines = textwrap.wrap(text, 22, break_long_words=True)
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

def add_caption(file: io.BytesIO, caption: Image.Image):
    """Adds a caption onto a given file"""
    file: Image.Image = Image.open(file)
    
    # create a new image that contains both the caption and the original image
    new_img = Image.new('RGBA', (file.width, file.height + caption.height))
    new_img.paste(caption, (0,0))
    new_img.paste(file, (0, caption.height))

    # save the result
    img_byte_arr = io.BytesIO()
    new_img.save(img_byte_arr, format = 'png')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result