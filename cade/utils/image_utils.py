#!/usr/bin/env python
# coding: utf-8

# Copyright 2011 Álvaro Justen [alvarojusten at gmail dot com]
# License: GPL <http://www.gnu.org/copyleft/gpl.html>

from pilmoji.core import Image, ImageDraw, ImageFont
import pilmoji.core as PIL


class ImageText(object):
    def __init__(
        self,
        data,
        mode="RGBA",
        background=(0, 0, 0, 0),
        encoding="utf8",
    ):
        if isinstance(data, str):
            self.filename = data
            self.image = Image.open(self.filename)
            self.size = self.image.size
        elif isinstance(data, (list, tuple)):
            self.size = data
            self.image = Image.new(mode, self.size, color=background)
            self.filename = None
        elif isinstance(data, PIL.Image.Image):
            self.image = data
            self.size = self.image.size
            self.filename = None
        self.draw = ImageDraw.Draw(self.image)
        self.encoding = encoding

    def save(self, filename=None):
        self.image.save(filename or self.filename)

    def show(self):
        self.image.show()

    def get_font_size(self, text, font, max_width=None, max_height=None):
        if max_width is None and max_height is None:
            raise ValueError("You need to pass max_width or max_height")
        font_size = 1
        text_size = self.get_text_size(font, font_size, text)
        if (max_width is not None and text_size[0] > max_width) or (
            max_height is not None and text_size[1] > max_height
        ):
            raise ValueError("Text can't be filled in only (%dpx, %dpx)" % text_size)
        while True:
            if (max_width is not None and text_size[0] >= max_width) or (
                max_height is not None and text_size[1] >= max_height
            ):
                return font_size - 1
            font_size += 1
            text_size = self.get_text_size(font, font_size, text)

    def write_text(
        self,
        xy,
        text,
        font_filename,
        font_size=11,
        color=(0, 0, 0),
        max_width=None,
        max_height=None,
    ):
        x, y = xy
        if font_size == "fill" and (max_width is not None or max_height is not None):
            font_size = self.get_font_size(text, font_filename, max_width, max_height)
        text_size = self.get_text_size(font_filename, font_size, text)
        font = ImageFont.truetype(font_filename, font_size)
        if x == "center":
            x = (self.size[0] - text_size[0]) / 2
        if y == "center":
            y = (self.size[1] - text_size[1]) / 2
        self.draw.text((x, y), text, font=font, fill=color)
        return text_size

    def get_text_size(self, font_filename, font_size, text):
        font = ImageFont.truetype(font_filename, font_size)
        return [int(_) for _ in font.getbbox(text)[-2:]]

    def write_multi_line_text_box(
        self,
        xy,
        text: str,
        box_width,
        font_filename,
        font_size=11,
        color=(0, 0, 0),
        place="left",
        justify_last_line=False,
        position="top",
        line_spacing=1.0,
    ):
        x, y = xy
        print(box_width)
        print(line_spacing)

        for l in text.splitlines():
            if l == "":
                y += (
                    self.get_text_size(font_filename, font_size, "dummy")[1]
                    * line_spacing
                )
            else:
                _, h = self.write_text_box(
                    (x, y),
                    l,
                    box_width,
                    font_filename,
                    font_size,
                    color,
                    place,
                    justify_last_line,
                    position,
                    line_spacing=10,
                )

            y += h
        return (box_width, y)

    def write_text_box(
        self,
        xy,
        text,
        box_width,
        font_filename,
        font_size=11,
        color=(0, 0, 0),
        place="left",
        justify_last_line=False,
        position="top",
        line_spacing=1.0,
    ):
        x, y = xy
        lines = []
        line = []
        words = text.split()
        for word in words:
            new_line = " ".join(line + [word])
            size = self.get_text_size(font_filename, font_size, new_line)
            text_height = size[1] * line_spacing
            last_line_bleed = text_height - size[1]
            if size[0] <= box_width:
                line.append(word)
            else:
                lines.append(line)
                line = [word]
        if line:
            lines.append(line)
        lines = [" ".join(line) for line in lines if line]

        match position:
            case "middle":
                height = (self.size[1] - len(lines) * text_height + last_line_bleed) / 2
                height -= text_height  # the loop below will fix this height
            case "bottom":
                height = self.size[1] - len(lines) * text_height + last_line_bleed
                height -= text_height  # the loop below will fix this height
            case _:
                height = y

        for index, line in enumerate(lines):
            height += text_height

            match place:
                case "left":
                    self.write_text((x, height), line, font_filename, font_size, color)
                case "right":
                    total_size = self.get_text_size(font_filename, font_size, line)
                    x_left = x + box_width - total_size[0]
                    self.write_text(
                        (x_left, height), line, font_filename, font_size, color
                    )
                case "center":
                    total_size = self.get_text_size(font_filename, font_size, line)
                    x_left = int(x + ((box_width - total_size[0]) / 2))
                    self.write_text(
                        (x_left, height), line, font_filename, font_size, color
                    )
                case "justify":
                    words = line.split()
                    if (index == len(lines) - 1 and not justify_last_line) or len(
                        words
                    ) == 1:
                        self.write_text(
                            (x, height), line, font_filename, font_size, color
                        )
                        continue
                    line_without_spaces = "".join(words)
                    total_size = self.get_text_size(
                        font_filename, font_size, line_without_spaces
                    )
                    space_width = (box_width - total_size[0]) / (len(words) - 1.0)
                    start_x = x
                    for word in words[:-1]:
                        self.write_text(
                            (start_x, height), word, font_filename, font_size, color
                        )
                        word_size = self.get_text_size(font_filename, font_size, word)
                        start_x += word_size[0] + space_width
                    last_word_size = self.get_text_size(
                        font_filename, font_size, words[-1]
                    )
                    last_word_x = x + box_width - last_word_size[0]
                    self.write_text(
                        (last_word_x, height),
                        words[-1],
                        font_filename,
                        font_size,
                        color,
                    )

        return (box_width, height - y)
