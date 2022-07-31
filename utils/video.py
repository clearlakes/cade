from utils.image import _get_content_bounds
from utils.functions import run
from utils.enums import ff

from tempfile import NamedTemporaryFile as create_temp, TemporaryDirectory
from io import BytesIO
from PIL import Image
import numpy
import cv2

def get_size(file: BytesIO):
    """Gets the dimensions of the video in a list format"""
    result, returncode = run(ff.GET_DIMENSIONS.value('-'), file.getvalue())

    if returncode != 0:
        return

    # turn bytes into characters and split the width and height
    result = result.decode("utf-8").split("x")
    result = list(map(int, result))

    return result

def resize(file: BytesIO, new_size: tuple[int]):
    """Resizes the video to the specified size"""
    with create_temp(suffix = ".mp4") as temp:
        temp.write(file.getvalue())

        # resize the video using the given size (and replace "auto" with -2, which means the same thing for ffmpeg)
        result, returncode = run(ff.RESIZE.value(temp.name, new_size))

        if returncode != 0:
            return

        result = BytesIO(result)

    return result

def caption(file: BytesIO, caption: Image.Image):
    """Captions the video using a caption image"""
    # convert caption image to cv2 image
    c_img = cv2.cvtColor(numpy.array(caption), cv2.COLOR_RGB2BGR)
    
    with TemporaryDirectory() as temp:
        input_video = f"{temp}/input.mp4"

        with open(input_video, "wb") as v_file:
            v_file.write(file.getvalue())
        
        # get first frame of video and its fps
        video = cv2.VideoCapture(input_video)
        success, frame = video.read()
        fps = video.get(cv2.CAP_PROP_FPS)

        i = 0
        # save each frame and add the caption on top
        while success:
            new_frame = cv2.vconcat([c_img, frame])
            cv2.imwrite(f"{temp}/{i}.png", new_frame)

            success, frame = video.read()
            i += 1

        video.release()
        
        # make new frames into a video and add audio from original file
        result, returncode = run(ff.CREATE_MP4.value(temp, fps, "input.mp4"))

        if returncode != 0:
            return

        with open(f"{temp}/output.mp4", "rb") as output:
            result = BytesIO(output.read())

    return result

def uncaption(file: BytesIO):
    """Removes captions from the video"""
    with TemporaryDirectory() as temp:
        input_video = f"{temp}/input.mp4"

        with open(input_video, "wb") as v_file:
            v_file.write(file.getvalue())
        
        # get first frame of video and its fps
        video = cv2.VideoCapture(input_video)
        success, frame = video.read()
        fps = video.get(cv2.CAP_PROP_FPS)

        x, y, w, h = _get_content_bounds(frame)

        i = 0
        while success:
            cropped_frame = frame[y:y+h, x:x+w]
            cv2.imwrite(f"{temp}/{i}.png", cropped_frame)

            success, frame = video.read()
            i += 1
        
        video.release()

        result, returncode = run(ff.CREATE_MP4.value(temp, fps, "input.mp4"))

        if returncode != 0:
            return

        with open(f"{temp}/output.mp4", "rb") as output:
            result = BytesIO(output.read())

    return result
