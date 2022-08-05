from utils.image import _get_content_bounds
from utils.dataclasses import ff
from utils.functions import run

from tempfile import NamedTemporaryFile as create_temp, TemporaryDirectory
from io import BytesIO
from PIL import Image
import numpy
import cv2

class EditVideo:
    def __init__(self, video: BytesIO):
        self.video = video

    def _get_frames(self, dir):
        """Returns the fps and frames of a video for editing"""
        input_video = f"{dir}/input.mp4"

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

    def _create_from_frames(self, dir, fps):
        """Creates a video using all images in a directory"""
        # make new frames into a video and add audio from original file
        _, returncode = run(ff.CREATE_MP4(dir, fps, "input.mp4"))

        if returncode != 0:
            return

        with open(f"{dir}/output.mp4", "rb") as output:
            return BytesIO(output.read())

    def resize(self, new_size: tuple[int]):
        """Resizes the video to the specified size"""
        with create_temp(suffix = ".mp4") as temp:
            temp.write(self.video.getvalue())

            # resize the video using the given size (and replace "auto" with -2, which means the same thing for ffmpeg)
            result, returncode = run(ff.RESIZE(temp.name, new_size))

            if returncode != 0:
                return

            result = BytesIO(result)

        return result

    def caption(self, caption: Image.Image):
        """Captions the video using a caption image"""
        # convert caption image to cv2 image
        c_img = cv2.cvtColor(numpy.array(caption), cv2.COLOR_RGB2BGR)
        
        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)

            # save each frame and add the caption on top
            for i, frame in enumerate(frames):
                new_frame = cv2.vconcat([c_img, frame])
                cv2.imwrite(f"{temp}/{i}.png", new_frame)
            
            result = self._create_from_frames(temp, fps)

        return result

    def uncaption(self):
        """Removes captions from the video"""
        with TemporaryDirectory() as temp:
            fps, frames = self._get_frames(temp)

            x, y, w, h = _get_content_bounds(frames[0])

            for i, frame in enumerate(frames):
                # crop each frame down to its content
                cropped_frame = frame[y:y+h, x:x+w]
                cv2.imwrite(f"{temp}/{i}.png", cropped_frame)
            
            result = self._create_from_frames(temp, fps)

        return result

def get_size(video: BytesIO):
    """Gets the dimensions of a video"""
    result, returncode = run(ff.GET_DIMENSIONS('-'), video.getvalue(), decode = True)

    if returncode != 0:
        return

    # turn bytes into characters and split the width and height
    result = result.split("x")
    result = tuple(map(int, result))

    return result