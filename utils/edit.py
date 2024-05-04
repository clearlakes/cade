import textwrap
from io import BytesIO
from shlex import split
from subprocess import PIPE, Popen
from tempfile import TemporaryDirectory
from typing import Callable

import cv2
import emoji
import numpy
from PIL import Image, ImageFont
from pilmoji import Pilmoji
from wand.color import Color as WColor
from wand.font import Font as WFont
from wand.image import Image as WImage

from .useful import AttObj, get_media_kind, run_async, run_cmd
from .vars import ff


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
    def create_caption_from_text(self, text: str, width: int):
        """creates the caption image (white background with black text)"""
        spacing = width // 40
        font_size = width // 10
        font_path = "fonts/futura.ttf"

        # replace ellipsis characters
        text = text.replace("…", "...")

        # wrap caption text
        caption_lines = textwrap.wrap(
            text, 21, replace_whitespace=False, drop_whitespace=False
        )
        caption = "\n".join(caption_lines)

        font = ImageFont.truetype(font_path, font_size)

        # get the size of the rendered text
        text_height = font.getsize_multiline(caption, spacing=spacing)[1] + font_size

        # get all emojis in text
        emojis = emoji.distinct_emoji_list(caption)

        if emojis:
            # create a blank image using the given width and the text height
            caption_img = Image.new("RGB", (width, text_height), (255, 255, 255))
            x, _ = caption_img.width // 2, caption_img.height // 2

            with Pilmoji(caption_img) as pilmoji:
                line_sizes = [
                    pilmoji.getsize(
                        line, font, spacing=spacing, emoji_scale_factor=1.25
                    )
                    for line in caption_lines
                ]

                for i, (line, size) in enumerate(zip(caption_lines, line_sizes)):
                    # align text line to the center horizontally (x) and from the top downwards (y)
                    x_offset = x + (size[0] // -2)
                    y_offset = round(size[1] / 2.5) + ((size[1] + spacing) * i)

                    pilmoji.text(
                        (x_offset, y_offset),
                        line,
                        (0, 0, 0),
                        font,
                        spacing=spacing,
                        emoji_scale_factor=1.25,
                    )
        else:
            with WImage(
                width=width, height=text_height, background=WColor("#fff")
            ) as img:
                img.font = WFont(font_path, font_size)
                img.caption(caption, gravity="center")

                caption_img = Image.open(BytesIO(img.make_blob("png")))

        return caption_img

    def get_content_bounds(self, img: Image.Image | cv2.Mat):
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
        big_contour = max(contours, key=cv2.contourArea)
        _, y, _, _ = cv2.boundingRect(big_contour)

        bounds = 0, y, img.shape[1], img.shape[0]

        return bounds


class EditImage(_Base):
    def __init__(self, image: AttObj):
        self.filename = image.filename
        self.file = Image.open(image.filebyte).convert("RGBA")
        self.dimensions = self.file.size

    def _save(self, img_format: str = "png", quality: int = 95):
        """general function for saving images as byte objects"""
        # save the image as bytes
        img_byte_arr = BytesIO()
        self.file.save(img_byte_arr, img_format, quality=quality)
        result = BytesIO(img_byte_arr.getvalue())

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
        background = Image.new("RGBA", small, (0, 0, 0))
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
        width, height = self.dimensions
        caption = self.create_caption_from_text(text, width)

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
        bounds = self.get_content_bounds(self.file)

        self.file = self.file.crop(bounds)

        result = self._save()
        return result


class EditGif(_Base):
    def __init__(self, gif: AttObj):
        self.filename = gif.filename
        self.file = Image.open(gif.filebyte)
        self.dimensions = self.file.size
        self.last_frame = self.file.convert("RGBA")
        self.mode = self._analyse()

        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.i = 0

    def _analyse(self):
        """determines if the gif's mode is full (changes whole frame) or partial (changes parts of the frame)"""
        # taken from https://gist.github.com/rockkoca/30357703f42f9d17c6fa121cf4dd1d8e
        try:
            while True:
                # check update region dimensions
                if self.file.tile and self.file.tile[0][1][2:] != self.dimensions:
                    return "partial"

                # move to next frame
                self.file.seek(self.file.tell() + 1)
        except EOFError:
            pass

        return "full"

    def _next_frame(self):
        """seeks to the next frame in the gif"""
        self.file.seek(self.i)
        self.new_frame = Image.new("RGBA", self.dimensions)

        if self.mode == "partial":
            self.new_frame.paste(self.last_frame)

        self.new_frame.paste(self.file, (0, 0), self.file.convert("RGBA"))

    def _append_frame(self, image: Image.Image, delay: int = 0):
        """appends the given frame to a list (along with its duration"""
        self.frames.append(image)
        self.last_frame = self.new_frame

        self.durations.append(delay if delay else self.file.info["duration"])

    def _save(self) -> tuple[BytesIO, str, str]:
        """converts the saved images into a gif byte object"""
        with TemporaryDirectory() as temp:
            cmd = "convert -loop 0 -alpha set -dispose 2 "

            # save each frame and add them to the command
            for i, (frame, delay) in enumerate(zip(self.frames, self.durations)):
                saved_path = f"{temp}/{i}.png"
                frame.save(saved_path)

                cmd += f"-delay {delay // 10} {saved_path} "

            # read output as bytes
            cmd += " gif:-"

            p = Popen(split(cmd), stdout=PIPE)
            result = BytesIO(p.communicate()[0])

        return (result, f"{self.filename}.gif", "image/gif")

    @run_async
    def resize(self, new_size: tuple[int, int]):
        """resizes the gif to a given size"""
        for self.i in range(self.file.n_frames):
            self._next_frame()

            # resize frame
            resized_frame = self.new_frame.resize(new_size)

            self._append_frame(resized_frame)

        result = self._save()
        return result

    @run_async
    def caption(self, text: str):
        """captions the gif"""
        # create caption
        caption = self.create_caption_from_text(text, self.dimensions[0])

        for self.i in range(self.file.n_frames):
            self._next_frame()

            # create image that will contain both caption and original frame
            captioned_frame = Image.new(
                "RGBA", (self.new_frame.width, self.new_frame.height + caption.height)
            )

            # add caption and then original frame under it
            captioned_frame.paste(caption, (0, 0))
            captioned_frame.paste(self.new_frame, (0, caption.height))

            self._append_frame(captioned_frame)

        result = self._save()
        return result

    @run_async
    def uncaption(self):
        """removes captions from the gif"""
        self._next_frame()
        bounds = self.get_content_bounds(self.new_frame)

        for self.i in range(self.file.n_frames):
            self._next_frame()
            cropped_frame = self.new_frame.crop(bounds)
            self._append_frame(cropped_frame)

        result = self._save()
        return result

    @run_async
    def speed(self, amount: float):
        "Speeds up the gif by a specified amount"
        for self.i in range(self.file.n_frames):
            self._next_frame()

            # reduce frame duration (divide by amount)
            new_delay = int(self.file.info["duration"] // amount)
            self._append_frame(self.new_frame, delay=new_delay)

        # start reducing frames instead if smallest duration (20) is reached
        if all(x <= 20 for x in self.durations):
            self.frames = self.frames[::2]
            self.durations = [20 for _ in range(len(self.frames))]

        result = self._save()
        return result


class EditVideo(_Base):
    def __init__(self, video: AttObj):
        self.filename = video.filename
        self.video = video.filebyte
        self.dimensions = (None, None)

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
        caption = self.create_caption_from_text(text, width)
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
            x, y, w, h = self.get_content_bounds(frames[0])

            for i, frame in enumerate(frames):
                # crop each frame down to its content
                cropped_frame = frame[y : y + h, x : x + w]
                cv2.imwrite(f"{temp}/{i}.png", cropped_frame)

            self.video = await self._create_from_frames(temp, fps)

        result = self._save()
        return result
