# <img src='https://i.imgur.com/yxm0XNL.gif' width='20'> cade commands <img src='https://i.imgur.com/yxm0XNL.gif' width='20'>
-  arguments starting with `*` are optional<br>
-  command prefix might be different depending on the server<br>
-  each command is linked to where their code is

[**Music**](#music) • [**Media**](#media) • [**General**](#general) • [**Funny**](#funny)


## Music
-  [**`.play`**](https://github.com/source64/cade/blob/main/cogs/music.py#L80) - plays a track/playlist from youtube or spotify
   -  how to use: `.play [url/query]`

-  [**`.join`**](https://github.com/source64/cade/blob/main/cogs/music.py#L132) - makes the bot join a voice channel

-  [**`.disconnect`**](https://github.com/source64/cade/blob/main/cogs/music.py#L148) - makes the bot leave a voice channel

-  [**`.skip`**](https://github.com/source64/cade/blob/main/cogs/music.py#L163) - skips the current track (or queued tracks)
   -  how to use: `.skip *[index]/all`

-  [**`.shuffle`**](https://github.com/source64/cade/blob/main/cogs/music.py#L244) - shuffles the order of the queue

-  [**`.loop`**](https://github.com/source64/cade/blob/main/cogs/music.py#L262) - begins/stops looping the current track

-  [**`.loopcount`**](https://github.com/source64/cade/blob/main/cogs/music.py#L280) - shows how many times the current track has been looped

-  [**`.playlist`**](https://github.com/source64/cade/blob/main/cogs/music.py#L292) - lists every playlist and the controls for each
   -  how to use: `.playlist *[playlist]`

-  [**`.pause`**](https://github.com/source64/cade/blob/main/cogs/music.py#L313) - pauses/unpauses the current track

-  [**`.seek`**](https://github.com/source64/cade/blob/main/cogs/music.py#L327) - skips to a specific point in the current track
   -  how to use: `.seek [time]`

-  [**`.queue`**](https://github.com/source64/cade/blob/main/cogs/music.py#L377) - lists all of the tracks in the queue

-  [**`.nowplaying`**](https://github.com/source64/cade/blob/main/cogs/music.py#L391) - shows information about the current track


## Media
-  [**`.jpeg`**](https://github.com/source64/cade/blob/main/cogs/media.py#L45) - lowers the quality of the given image
   -  how to use: `.jpeg (image)`

-  [**`.imgaudio`**](https://github.com/source64/cade/blob/main/cogs/media.py#L59) - converts an image into a video with audio
   -  how to use: `.imgaudio *[seconds] (image)`

-  [**`.resize`**](https://github.com/source64/cade/blob/main/cogs/media.py#L185) - resizes the given attachment
   -  how to use: `.resize [width]/auto *[height]/auto (gif/image/video)`

-  [**`.caption`**](https://github.com/source64/cade/blob/main/cogs/media.py#L226) - captions the specified gif or image in the style of iFunny's captions
   -  how to use: `.caption [text] (gif/image/video)`

-  [**`.uncaption`**](https://github.com/source64/cade/blob/main/cogs/media.py#L238) - removes the caption from the given attachment
   -  how to use: `.uncaption (gif/image/video)`

-  [**`.speed`**](https://github.com/source64/cade/blob/main/cogs/media.py#L250) - speeds up a gif/video by a given amount (1.25x by default)
   -  how to use: `.speed *[multiplier] (gif/video)`

-  [**`.get`**](https://github.com/source64/cade/blob/main/cogs/media.py#L273) - downloads a youtube video (or a part of it)
   -  how to use: `.get [youtube-url] *[start-time] *[end-time]`


## General
-  [**`.info`**](https://github.com/source64/cade/blob/main/cogs/general.py#L77) - get information about the bot

-  [**`.help`**](https://github.com/source64/cade/blob/main/cogs/general.py#L119) - see a list of commands
   -  how to use: `.help *[command]`

-  [**`.tag`**](https://github.com/source64/cade/blob/main/cogs/general.py#L159) - sends/creates a tag containing a given message
   -  how to use: `.tag [tag-name] *[message]`

-  [**`.tagdelete`**](https://github.com/source64/cade/blob/main/cogs/general.py#L183) - deletes the specified tag if it exists
   -  how to use: `.tagdelete [tag-name]`

-  [**`.taglist`**](https://github.com/source64/cade/blob/main/cogs/general.py#L200) - lists every tag in the server

-  [**`.welcome`**](https://github.com/source64/cade/blob/main/cogs/general.py#L214) - sets the welcome message for the server (admin)
   -  how to use: `.welcome [channel] *[message]`

-  [**`.setprefix`**](https://github.com/source64/cade/blob/main/cogs/general.py#L235) - sets the bot prefix for the server (admin)
   -  how to use: `.setprefix [prefix]`


## Funny
> note: these commands are specific to funny museum
-  [**`.tweet`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L51) - tweets out a message
   -  how to use: `.tweet [message]`

-  [**`.reply`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L68) - replies to a given tweet by its url/id (or the latest tweet)
   -  how to use: `.reply [tweet-id]/latest [message]`

-  [**`.profile`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L125) - replaces the profile/banner of the twita account
   -  how to use: `.profile profile/banner (image)`