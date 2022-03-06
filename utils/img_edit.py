from PIL import Image, ImageFont, ImageDraw
import textwrap
import io

def get_size(file: io.BytesIO):
    image = Image.open(file)
    size = image.width, image.height
    
    return size

def size_check(file: io.BytesIO):
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
    alpha_composite.save(img_byte_arr, format='PNG')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def gif(file: io.BytesIO, edit_type: int, size: tuple = None, caption: Image.Image = None):
    """ Function for editing gifs (and either resize or caption them) """
    file = Image.open(file)
    
    def analyseImage(file: Image.Image):
        # determine if the gif's mode is full (changes whole frame) or additive (changes parts of the frame)
        # taken from https://gist.github.com/rockkoca/30357703f42f9d17c6fa121cf4dd1d8e
        results = {'size': file.size, 'mode': 'full'}

        try:
            while True:
                if file.tile:
                    tile = file.tile[0]
                    update_region = tile[1]
                    update_region_dimensions = update_region[2:]

                    if update_region_dimensions != file.size:
                        results['mode'] = 'partial'
                        break

                # move to next frame    
                file.seek(file.tell() + 1)
        except EOFError:
            pass

        return results
    
    analyse = analyseImage(file)

    i = 0
    frame_num = 0
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
                final_caption = Image.new('RGB', (new_frame.width, new_frame.height + caption.height))

                final_caption.paste(caption, (0, 0))
                final_caption.paste(new_frame, (0, caption.height))

                frames.append(final_caption)

            # add the frame's duration to a list
            durations.append(file.info["duration"])

            i += 1
            frame_num += 1
            last_frame = new_frame
            file.seek(frame_num)
    except EOFError:
        pass

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
    file_rgb.save(img_byte_arr, format='JPEG', quality = 4) # "quality = 4" lowers the quality
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def resize(file: io.BytesIO, size: tuple[int, int]):
    # resize the file
    file = Image.open(file)
    file = file.resize(size)

    img_byte_arr = io.BytesIO()
    file.save(img_byte_arr, format='png')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result

def create_caption(text: str, width: int):
    # wrap the caption text
    wrap_length = 25
    caption_lines = textwrap.wrap(text, wrap_length, break_long_words=True)
    caption_text = "\n".join(caption_lines)

    # caption background color
    white = (255,255,255)

    # function for getting the font size using the given width ratio
    # from https://stackoverflow.com/a/66091387
    def find_font_size(text, font, image, target_width_ratio):
        tested_font = ImageFont.truetype(font, 1)
        observed_width, _ = get_text_size(text, image, tested_font)
        estimated_font_size = 1 / ((observed_width) / image.width) * target_width_ratio
        return round(estimated_font_size)

    # function for getting the text size by seeing what the output is when text is drawn on the image
    def get_text_size(text, image, font):
        im = Image.new('RGB', (image.width, image.height))
        draw = ImageDraw.Draw(im)
        return draw.textsize(text, font)

    # get the appropriate width ratio to use depending on how many lines of text there are
    if len(caption_lines) == 1:
        width_ratio = 0.7
    elif len(caption_lines) == 2:
        width_ratio = 0.8
    elif len(caption_lines) >= 3:
        width_ratio = 1.1

    # calculate the height of the caption image
    height = (round(width / 5) + ((round(width / (5 + width_ratio)) * (len(caption_lines) - 1))))

    # "c" is the caption image itself, using the variables from above
    caption = Image.new('RGB', (width, height), white)

    # get the font
    font_path = "fonts/roboto.otf"
    font_size = find_font_size(caption_text, font_path, caption, width_ratio)

    editable_img = ImageDraw.Draw(caption)
    image_w, image_h = caption.size

    # shrink the font size if the text height is larger than the image's height
    while True:
        font = ImageFont.truetype(font_path, font_size)
        text_w, text_h = editable_img.textsize(caption_text, font = font)

        if text_h >= (image_h - 10):
            font_size -= 1
        else:
            break
    
    # decrease the wrap length if the text width is larger than the image's width
    while True:
        font = ImageFont.truetype(font_path, font_size)
        text_w, text_h = editable_img.textsize(caption_text, font = font)

        if text_w >= (image_w - 20):
            wrap_length -= 1
            caption_lines = textwrap.wrap(caption_text, wrap_length, break_long_words=True)
            caption_text = "\n".join(caption_lines)
        else:
            break
    
    # draw the text onto the image
    xy = (image_w) // 2, (image_h) // 2
    editable_img.text(xy, caption_text, font=font, fill=(0,0,0), anchor="mm", align="center")

    return caption

def add_caption(file: io.BytesIO, caption: Image.Image):
    file = Image.open(file)

    new_img = Image.new('RGB', (file.width, file.height + caption.height))
    new_img.paste(caption, (0,0))
    new_img.paste(file, (0, caption.height))

    img_byte_arr = io.BytesIO()
    new_img.save(img_byte_arr, format='png')
    result = io.BytesIO(img_byte_arr.getvalue())

    return result