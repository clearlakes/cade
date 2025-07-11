from io import BytesIO
from tempfile import TemporaryDirectory
from typing import Callable

import cv2
import numpy
from PIL import Image, ImageFont, ImageSequence
from pilmoji import Pilmoji

from .useful import AttObj, get_media_kind, run_async, run_cmd
from .vars import ff, reg

FONT_PATH = "fonts/futura.ttf"
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

def edit(res: AttObj):
    """gets the edit class for the given file"""
    kind = get_media_kind(res.filetype)

    match kind:
        case "gif":
            return EditGif(res)
        case "image":
            return EditImage(res)
        case "video":
            return EditVideo(res)


class _Base:
    def _wrap_text(self, font: ImageFont.FreeTypeFont, text: str, width: int) -> str:
        """wraps text to fit in a caption"""
        available_width = width - (width // 12)
        pre_wrap_lines = text.splitlines()
        wrapped_lines = []

        i = 0
        while i < len(pre_wrap_lines):
            line = pre_wrap_lines[i]
            words = line.split(" ")
            current_line = ""
            word_index = 0

            while word_index < len(words):
                test_line = (current_line + " " + words[word_index]).strip()
                line_width = font.getlength(test_line)

                # compare rendered width with available width
                if line_width <= available_width:
                    current_line = test_line
                    word_index += 1
                else:
                    # splitting long words by character
                    if current_line == "":
                        long_word = words[word_index]
                        split_index = 0
                        partial = ""

                        for j, char in enumerate(long_word):
                            test_partial = partial + char

                            if font.getlength(test_partial + "-") > available_width:
                                break

                            partial = test_partial
                            split_index = j

                        if split_index == 0:
                            split_index = 1
                            partial = long_word[:1]

                        current_line = partial + "-"
                        words[word_index] = long_word[split_index + 1 :]
                    else:
                        break

            wrapped_lines.append(current_line.strip())

            remaining = " ".join(words[word_index:])

            if remaining:
                pre_wrap_lines.insert(i + 1, remaining)

            i += 1

        return "\n".join(wrapped_lines)
    
    def create_caption_header(self, text: str, width: int):
        """creates the caption image (white background with black text)"""
        spacing = width // 40
        font_size = width // 10
        emoji_scale = 1.2
        emoji_offset = (font_size // 12, -(font_size // 6))

        # replace ellipsis characters
        text = text.replace("…", "...")

        # make discord emoji placeholders (prevents wrap from breaking them)
        discord_emojis = {}
        for i, de in enumerate(reg.DISCORD_EMOJI.findall(text)):
            text = text.replace(de, f"[#{i}#]")
            discord_emojis[i] = de

        font = ImageFont.truetype(
            FONT_PATH, font_size, layout_engine=ImageFont.Layout.RAQM
        )

        # wrap caption text
        caption = self._wrap_text(font, text, width)

        # undo discord emoji placeholders
        for i, dep in enumerate(reg.DE_PLACEHOLDER.findall(caption)):
            caption = caption.replace(dep, discord_emojis[i])

        if discord_emojis:
            de_string = list(discord_emojis.values())

            if caption.replace(" ", "") in "".join(de_string):
                emoji_scale = 1.5
                emoji_offset = -emoji_offset[1]
                emoji_offset = (emoji_offset[0], int(width // -40))

        # get the size of the rendered text
        with Pilmoji(Image.new("RGB", (1, 1), WHITE)) as pilmoji:
            rendered_height = pilmoji.getsize(
                text=caption,
                font=font,
                spacing=spacing,
                emoji_scale_factor=emoji_scale,
            )[1]

            text_height = rendered_height + font_size

        caption_img = Image.new("RGB", (width, text_height), WHITE)
        x, y = caption_img.width // 2, caption_img.height // 2

        with Pilmoji(caption_img) as pilmoji:
            pilmoji.text(
                (x, y),
                caption,
                fill=BLACK,
                font=font,
                align="center",
                anchor="mm",
                spacing=spacing,
                emoji_scale_factor=emoji_scale,
                emoji_position_offset=emoji_offset,
            )

        return caption_img

    def _get_content_bounds(self, frame: Image.Image | cv2.Mat):
        """gets the largest congruent part of the frame without the caption"""
        # convert PIL image to cv2 image
        if isinstance(frame, Image.Image):
            frame = cv2.cvtColor(numpy.array(frame), cv2.COLOR_RGB2BGR)

        # invert the frame and convert it to grayscale
        frame = cv2.cvtColor(cv2.bitwise_not(frame), cv2.COLOR_BGR2GRAY)

        # get morph of grayscale image in order to better separate the caption
        thresh = cv2.threshold(frame, 1, 255, cv2.THRESH_BINARY)[1]
        morph_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, morph_rect)

        # finding the largest contour (actual content of the frame)
        contours = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]

        largest_area = max(contours, key=cv2.contourArea)
        _, y, _, _ = cv2.boundingRect(largest_area)

        # part of frame to crop
        bounds = 0, y, frame.shape[1], frame.shape[0]

        return bounds


class EditImage(_Base):
    def __init__(self, image: AttObj):
        self.filename = image.filename
        self.file = Image.open(image.filebyte).convert("RGBA")

    def _save(self, img_format: str = "png", quality: int = 95):
        """general function for saving images as byte objects"""
        result = BytesIO()

        # save the image as bytes
        self.file.save(result, img_format, quality=quality)

        result.seek(0)
        self.file.close()

        return (result, f"{self.filename}.{img_format}", f"image/{img_format}")

    @run_async
    def jpeg(self) -> Callable[[], tuple[BytesIO, str, str]]:
        """returns a low quality version of the image"""
        file_rgba = self.file.convert("RGBA")

        # shrink the image to 80% of it's original size
        orig_w, orig_h = file_rgba.size
        small_w = round(0.8 * orig_w)
        small_h = round(0.8 * orig_h)
        small = (small_w, small_h)
        file_rgba = file_rgba.resize(small)

        # create a black background behind the image (useful if it's a transparent png)
        background = Image.new("RGBA", small, BLACK)
        alpha_composite = Image.alpha_composite(background, file_rgba)
        self.file = alpha_composite.convert("RGB")  # converting to RGB for jpeg output

        result = self._save("jpeg", 4)
        return result

    @run_async
    def resize(self, new_size: tuple[int, int]):
        """resizes the image to a given size"""
        self.file = self.file.resize(new_size)

        result = self._save()
        return result

    @run_async
    def caption(self, text: str):
        """captions the image"""
        width, height = self.file.size
        caption = self.create_caption_header(text, width)

        # create a new image that contains both the caption and the original image
        new_img = Image.new("RGBA", (width, height + caption.height))

        new_img.paste(caption, (0, 0))
        new_img.paste(self.file, (0, caption.height))

        self.file = new_img

        result = self._save()
        return result

    @run_async
    def uncaption(self):
        """removes captions from the image"""
        bounds = self._get_content_bounds(self.file)

        self.file = self.file.crop(bounds)

        result = self._save()
        return result


class EditGif(_Base):
    def __init__(self, gif: AttObj):
        self.filename = gif.filename.split(".")[0]
        self.file = Image.open(gif.filebyte)
        self.file.seek(0)

        self.frame_duration = self.file.info["duration"]

        self.caption_header = None
        self.uncaption_crop = None
        self.speed_amount = None
        self.resize_value = None

    def _save(self, frames: list[Image.Image]) -> tuple[BytesIO, str, str]:
        """converts the saved images into a gif byte object"""
        result = BytesIO()

        # save the gif as bytes
        frames[0].save(
            result, 
            format="GIF", 
            save_all=True, 
            append_images=frames[1:], 
            optimize=False, 
            duration=self.frame_duration, 
            loop=0
        )

        self.file.close()
        result.seek(0)

        return (result, f"{self.filename}.gif", "image/gif")
    
    def _resize_process(self, frame: Image.Image) -> Image.Image:
        resized_frame = frame.resize(self.resize_value)
        return resized_frame
    
    def _caption_process(self, frame: Image.Image) -> Image.Image:
        # create image that will contain both caption and original frame
        captioned_frame = Image.new("RGB", (frame.width, frame.height + self.caption_header.height))

        # add caption and then original frame under it
        captioned_frame.paste(self.caption_header, (0, 0))
        captioned_frame.paste(frame, (0, self.caption_header.height))

        return captioned_frame
    
    def _uncaption_process(self, frame: Image.Image) -> Image.Image:
        cropped_frame = frame.crop(self.uncaption_crop)
        return cropped_frame
    
    def _no_process(self, frame: Image.Image) -> Image.Image:
        return frame
    
    def _process_frames(self, function) -> list[Image.Image]:
        return ImageSequence.all_frames(self.file, function)
    
    @run_async
    def resize(self, new_size: tuple[int, int]):
        """resizes the gif to a given size"""
        self.resize_value = new_size

        frames = self._process_frames(self._resize_process)
        result = self._save(frames)
        return result

    @run_async
    def caption(self, text: str):
        """captions the gif"""
        # create caption header
        self.caption_header = self.create_caption_header(text, self.file.size[0])

        frames = self._process_frames(self._caption_process)
        result = self._save(frames)
        return result

    @run_async
    def uncaption(self):
        """removes captions from the gif"""
        self.file.seek(1)
        self.uncaption_crop = self._get_content_bounds(self.file)

        frames = self._process_frames(self._uncaption_process)
        result = self._save(frames)
        return result

    @run_async
    def speed(self, amount: float):
        "speeds up the gif by a specified amount"
        self.frame_duration = int(self.file.info["duration"] // amount)

        frames = self._process_frames(self._no_process)
        result = self._save(frames)
        return result

    @run_async
    def reverse(self):
        """reverses the gif"""
        frames = self._process_frames(self._no_process)
        frames.reverse()

        result = self._save(frames)
        return result


class EditVideo(_Base):
    def __init__(self, video: AttObj):
        self.filename = video.filename
        self.video = video.filebyte

    async def _get_size(self) -> tuple[int, int]:
        """gets the dimensions of the video"""
        result, returncode = await run_cmd(
            ff.GET_DIMENSIONS, self.video.getvalue(), decode=True
        )

        if returncode != 0:
            return

        # turn bytes into characters and split the width and height
        result = result.split("x")
        result = tuple(map(int, result))

        return result

    def _get_frames(self, path):
        """returns the fps and frames of a video for editing"""
        input_video = f"{path}/input.mp4"

        with open(input_video, "wb") as v_file:
            v_file.write(self.video.getvalue())

        # get first frame of video and its fps
        video = cv2.VideoCapture(input_video)
        success, frame = video.read()

        frames = []
        fps = video.get(cv2.CAP_PROP_FPS)

        while success:
            frames.append(frame)
            success, frame = video.read()

        return fps, frames

    async def _create_from_frames(self, path, fps):
        """creates a video using all images in a directory"""
        # make new frames into a video and add audio from original file
        _, returncode = await run_cmd(ff.CREATE_MP4(path, fps))

        if returncode != 0:
            return

        with open(f"{path}/output.mp4", "rb") as output:
            return BytesIO(output.read())

    async def _run_ffmpeg(self, command: str, *args):
        with TemporaryDirectory() as temp:
            with open(f"{temp}/input.mp4", "wb") as input:
                input.write(self.video.getvalue())

            # resize the video using the given size
            _, returncode = await run_cmd(command(temp, *args))

            if returncode != 0:
                return

            with open(f"{temp}/output.mp4", "rb") as output:
                result_bytes = BytesIO(output.read())

        return result_bytes

    def _save(self) -> tuple[BytesIO | None, str, str]:
        return (self.video, f"{self.filename}.mp4", "video/mp4")

    async def resize(self, new_size: tuple[int, int]):
        """resizes the video to the specified size"""
        self.video = await self._run_ffmpeg(ff.RESIZE, *new_size)

        result = self._save()
        return result

    async def speed(self, amount: float):
        """speeds up the video by the given amount"""
        if amount < 0.5:
            amount = 0.5  # smallest multiplier for videos

        self.video = await self._run_ffmpeg(ff.SPEED_UP, amount)

        result = self._save()
        return result

    async def caption(self, text: str):
        """captions the video"""
        width, _ = await self._get_size()

        # get caption image and convert it into a cv2 image
        caption = self.create_caption_header(text, width)
        c_img = cv2.cvtColor(numpy.array(caption), cv2.COLOR_RGB2BGR)

        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)

            # save each frame and add the caption on top
            for i, frame in enumerate(frames):
                new_frame = cv2.vconcat([c_img, frame])
                cv2.imwrite(f"{temp}/{i}.png", new_frame)

            self.video = await self._create_from_frames(temp, fps)

        result = self._save()
        return result

    async def uncaption(self):
        """removes captions from the video"""
        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)
            x, y, w, h = self._get_content_bounds(frames[1])

            for i, frame in enumerate(frames):
                # crop each frame down to its content
                cropped_frame = frame[y : y + h, x : x + w]
                cv2.imwrite(f"{temp}/{i}.png", cropped_frame)

            self.video = await self._create_from_frames(temp, fps)

        result = self._save()
        return result
