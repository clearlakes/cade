# <img src='https://i.imgur.com/yxm0XNL.gif' width='20'> cade commands <img src='https://i.imgur.com/yxm0XNL.gif' width='20'>
arguments starting with `*` are optional<br>
(commands are linked to where their code is)

go to:&nbsp; [**Funny**](#funny) • [**General**](#general) • [**Media**](#media) • [**Music**](#music)

### Music
- [**`.play`**](https://github.com/source64/cade/blob/main/cogs/music.py#L81) - plays a track/playlist from youtube or spotify
	- how to use: `.play [url/query]`
- [**`.join`**](https://github.com/source64/cade/blob/main/cogs/music.py#L135) - makes the bot join a voice channel
- [**`.disconnect`**](https://github.com/source64/cade/blob/main/cogs/music.py#L151) - makes the bot leave a voice channel
- [**`.skip`**](https://github.com/source64/cade/blob/main/cogs/music.py#L166) - skips the current track (or queued tracks)
	- how to use: `.skip *[index]/all`
- [**`.shuffle`**](https://github.com/source64/cade/blob/main/cogs/music.py#L201) - shuffles the order of the queue
- [**`.loop`**](https://github.com/source64/cade/blob/main/cogs/music.py#L219) - begins/stops looping the current track
- [**`.loopcount`**](https://github.com/source64/cade/blob/main/cogs/music.py#L237) - shows how many times the current track has been looped
- [**`.playlist`**](https://github.com/source64/cade/blob/main/cogs/music.py#L249) - lists every playlist and the controls for each
	- how to use: `.playlist *[playlist]`
- [**`.pause`**](https://github.com/source64/cade/blob/main/cogs/music.py#L271) - pauses/unpauses the current track
- [**`.seek`**](https://github.com/source64/cade/blob/main/cogs/music.py#L285) - skips to a specific point in the current track
	- how to use: `.seek [time]`
- [**`.queue`**](https://github.com/source64/cade/blob/main/cogs/music.py#L339) - lists all of the tracks in the queue
- [**`.nowplaying`**](https://github.com/source64/cade/blob/main/cogs/music.py#L353) - shows information about the current track

### Media
- [**`.jpeg`**](https://github.com/source64/cade/blob/main/cogs/media.py#L34) - lowers the quality of the given image
	- how to use: `.jpeg (image)`
- [**`.imgaudio`**](https://github.com/source64/cade/blob/main/cogs/media.py#L52) - converts an image into a video with audio
	- how to use: `.imgaudio *[seconds] (image)`
- [**`.resize`**](https://github.com/source64/cade/blob/main/cogs/media.py#L201) - resizes the given attachment
	- how to use: `.resize [width]/auto *[height]/auto (gif/image/video)`
- [**`.caption`**](https://github.com/source64/cade/blob/main/cogs/media.py#L256) - captions the specified gif or image in the style of iFunny's captions
	- how to use: `.caption [text] (gif/image/video)`
- [**`.uncaption`**](https://github.com/source64/cade/blob/main/cogs/media.py#L296) - removes the caption from the given attachment
	- how to use: `.uncaption (gif/image/video)`
- [**`.get`**](https://github.com/source64/cade/blob/main/cogs/media.py#L323) - downloads a youtube video (or a part of it)
	- how to use: `.get [youtube-url] *[start-time] *[end-time]`

### General
- [**`.info`**](https://github.com/source64/cade/blob/main/cogs/general.py#L108) - get information about the bot
- [**`.help`**](https://github.com/source64/cade/blob/main/cogs/general.py#L161) - see a list of commands
	- how to use: `.help *[command]`
- [**`.echo`**](https://github.com/source64/cade/blob/main/cogs/general.py#L203) - repeats a message in the specified text channel
	- how to use: `.echo [channel] [message]`
- [**`.tag`**](https://github.com/source64/cade/blob/main/cogs/general.py#L224) - sends/creates a tag containing a given message
	- how to use: `.tag [tag] *[message]`
- [**`.tagdelete`**](https://github.com/source64/cade/blob/main/cogs/general.py#L278) - deletes the specified tag if it exists
	- how to use: `.tagdelete [tag]`
- [**`.taglist`**](https://github.com/source64/cade/blob/main/cogs/general.py#L298) - lists every tag in the server
- [**`.welcome`**](https://github.com/source64/cade/blob/main/cogs/general.py#L322) - sets the welcome message for the server
	- how to use: `.welcome [channel] *[message]`

### Funny
> note: these commands are specific to funny museum
- [**`.tweet`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L65) - tweets out a message
	- how to use: `.tweet [message]`
- [**`.reply`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L82) - replies to a given tweet by its url/id (or the latest tweet)
	- how to use: `.reply [tweet-id]/latest [message]`
- [**`.profile`**](https://github.com/source64/cade/blob/main/cogs/funny.py#L130) - replaces the profile/banner of the twita account
	- how to use: `.profile profile/banner (image)`
