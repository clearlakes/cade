# <img src='https://i.imgur.com/yxm0XNL.gif' width='20'> cade commands <img src='https://i.imgur.com/yxm0XNL.gif' width='20'>
-  arguments starting with `*` are optional<br>
-  command prefix might be different depending on the server<br>
-  each command is linked to where their code is

[**Music**](#music) • [**Misc**](#misc) • [**Media**](#media)


## Music
-  [**`.play`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L55) - plays a track/playlist from youtube or spotify
   -  how to use: `.play [url/query]`

-  [**`.join`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L107) - makes the bot join a voice channel

-  [**`.disconnect`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L123) - makes the bot leave a voice channel

-  [**`.skip`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L138) - skips the current track (or queued tracks)
   -  how to use: `.skip *[index]/all`

-  [**`.shuffle`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L238) - shuffles the order of the queue

-  [**`.loop`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L256) - begins/stops looping the current track

-  [**`.loopcount`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L274) - shows how many times the current track has been looped

-  [**`.pause`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L288) - pauses/unpauses the current track

-  [**`.seek`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L302) - skips to a specific point in the current track
   -  how to use: `.seek [time]`

-  [**`.queue`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L352) - lists all of the tracks in the queue

-  [**`.nowplaying`**](https://github.com/clearlakes/cade/blob/main/cogs/music.py#L366) - shows information about the current track


## Misc
-  [**`.info`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L126) - get information about the bot or a command
   -  how to use: `.info *[command]`

-  [**`.help`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L188) - see a list of commands
   -  how to use: `.help *[command]`

-  [**`.tag`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L235) - sends/creates a tag containing a given message
   -  how to use: `.tag [tag-name] *[message]`

-  [**`.tagdelete`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L259) - deletes the specified tag if it exists
   -  how to use: `.tagdelete [tag-name]`

-  [**`.taglist`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L276) - lists every tag in the server

-  [**`.welcome`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L290) - sets the welcome message for the server (admin)
   -  how to use: `.welcome [channel] *[message]`

-  [**`.setprefix`**](https://github.com/clearlakes/cade/blob/main/cogs/misc.py#L313) - sets the bot prefix for the server (admin)
   -  how to use: `.setprefix [prefix]`


## Media
-  [**`.jpeg`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L38) - lowers the quality of the given image
   -  how to use: `.jpeg (image)`

-  [**`.imgaudio`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L53) - converts an image into a video with audio
   -  how to use: `.imgaudio *[seconds] (image)`

-  [**`.resize`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L204) - resizes the given attachment
   -  how to use: `.resize [width]/auto *[height]/auto (gif/image/video)`

-  [**`.caption`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L246) - captions the specified gif or image in the style of iFunny's captions
   -  how to use: `.caption [text] (gif/image/video)`

-  [**`.uncaption`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L259) - removes the caption from the given attachment
   -  how to use: `.uncaption (gif/image/video)`

-  [**`.speed`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L272) - speeds up a gif/video by a given amount (1.25x by default)
   -  how to use: `.speed *[multiplier] (gif/video)`

-  [**`.get`**](https://github.com/clearlakes/cade/blob/main/cogs/media.py#L296) - downloads a youtube video (or a part of it)
   -  how to use: `.get [youtube-url] *[start-time] *[end-time]`