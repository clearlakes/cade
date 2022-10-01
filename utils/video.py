from utils.image import get_content_bounds
from utils.useful import AttObj, run_cmd
from utils.data import ff

from tempfile import TemporaryDirectory
from io import BytesIO
from PIL import Image
import numpy
import cv2

class EditVideo:
    def __init__(self, video: AttObj):
        self.filename = video.filename
        self.video = video.filebyte

    def _get_frames(self, path):
        """Returns the fps and frames of a video for editing"""
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
        """Creates a video using all images in a directory"""
        # make new frames into a video and add audio from original file
        _, returncode = await run_cmd(ff.CREATE_MP4(path, fps))

        if returncode != 0:
            return

        with open(f"{path}/output.mp4", "rb") as output:
            return BytesIO(output.read())

    async def _run_ffmpeg(self, path: str, command: str):
        with open(f"{path}/input.mp4", "wb") as input:
            input.write(self.video.getvalue())

        # resize the video using the given size
        _, returncode = await run_cmd(command)

        if returncode != 0:
            return

        with open(f"{path}/output.mp4", "rb") as output:
            result_bytes = BytesIO(output.read())

        return (result_bytes, f"{self.filename}.mp4")

    async def resize(self, new_size: tuple[int]):
        """Resizes the video to the specified size"""
        with TemporaryDirectory() as temp:
            result = await self._run_ffmpeg(temp, ff.RESIZE(temp, *new_size))

        return result

    async def speed(self, amount: float):
        """Speeds up the video by the given amount"""
        if amount < 0.5:
            amount = 0.5  # smallest multiplier for videos

        with TemporaryDirectory() as temp:
            result = await self._run_ffmpeg(temp, ff.SPEED_UP(temp, amount))

        return result

    async def caption(self, caption: Image.Image):
        """Captions the video using a caption image"""
        # convert caption image to cv2 image
        c_img = cv2.cvtColor(numpy.array(caption), cv2.COLOR_RGB2BGR)

        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)

            # save each frame and add the caption on top
            for i, frame in enumerate(frames):
                new_frame = cv2.vconcat([c_img, frame])
                cv2.imwrite(f"{temp}/{i}.png", new_frame)

            result = await self._create_from_frames(temp, fps)

        return (result, f"{self.filename}.mp4") if result else None

    async def uncaption(self):
        """Removes captions from the video"""
        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)

            x, y, w, h = get_content_bounds(frames[0])

            for i, frame in enumerate(frames):
                # crop each frame down to its content
                cropped_frame = frame[y:y+h, x:x+w]
                cv2.imwrite(f"{temp}/{i}.png", cropped_frame)

            result = await self._create_from_frames(temp, fps)

        return (result, f"{self.filename}.mp4") if result else None

async def get_video_size(video: BytesIO) -> tuple[int, int]:
    """Gets the dimensions of a video"""
    result, returncode = await run_cmd(ff.GET_DIMENSIONS, video.getvalue(), decode = True)

    if returncode != 0:
        return

    # turn bytes into characters and split the width and height
    result = result.split("x")
    result = tuple(map(int, result))

    return result