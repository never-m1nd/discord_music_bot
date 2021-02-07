import asyncio
import discord
from discord.ext import commands
import collections
import logging
import youtube_dl
import validators
from youtubesearchpython import VideosSearch


logging.basicConfig(level=logging.INFO)
TOKEN = ''


youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            play_list = []
            for video in data['entries']:
                filename = video['url'] if stream else ytdl.prepare_filename(data)
                play_list.append(cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=video))
            return play_list, True

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data), False


class MusicPlayer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.queue = collections.deque([])

    @commands.command()
    async def leave(self, ctx):
        await ctx.voice_client.disconnect()

    @staticmethod
    async def join(ctx):
        """Joins a voice channel"""
        connected = ctx.author.voice
        if connected and ctx.voice_client is None:
            await connected.channel.connect()
        elif ctx.voice_client is not None:
            await ctx.voice_client.move_to(connected.channel)
        else:
            await ctx.send("You need to connect to channel")
            return False
        return True

    @staticmethod
    async def find_song_url(query):
        if validators.url(query):
            url = query
        else:
            video_search = VideosSearch(query, limit=1)
            url = video_search.result()['result'][0]['link']
        return url

    @commands.command()
    async def play(self, ctx, *, song):
        joined = await self.join(ctx)
        if joined:
            url = await self.find_song_url(song)
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            if player[1]:
                for video in player[0]:
                    self.queue.append(video)
            else:
                self.queue.append(player[0])
            if ctx.voice_client.is_playing():
                await ctx.send('Song queued')
            else:
                self.next(ctx)

    def next(self, ctx):
        if self.queue:
            player = self.queue.popleft()
            ctx.voice_client.play(player, after=lambda e: self.next(ctx))
            asyncio.run_coroutine_threadsafe(ctx.send('Now playing: {}'.format(player.title)), self.bot.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.sleep(ctx), self.bot.loop)

    async def sleep(self, ctx):
        await asyncio.sleep(10)
        if not ctx.voice_client.is_playing():
            asyncio.run_coroutine_threadsafe(ctx.send("Empty queue"), self.bot.loop)
            asyncio.run_coroutine_threadsafe(ctx.voice_client.disconnect(), self.bot.loop)

    @commands.command()
    async def skip(self, ctx):
        if ctx.voice_client:
            ctx.voice_client.stop()

    @commands.command()
    async def clear(self, ctx):
        self.queue.clear()

    @commands.command()
    async def queue(self, ctx):
        if self.queue:
            for i, song in enumerate(self.queue):
                await ctx.send(str(i+1) + '.' + song.title)
        else:
            await ctx.send("Empty queue.")

    @commands.command(name='clear')
    async def clear(self, ctx):
        self.queue.clear()
        await ctx.send("Queue has been cleared")


bot = discord.ext.commands.Bot(command_prefix='!')


@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')


bot.add_cog(MusicPlayer(bot))
asyncio.run(bot.run(TOKEN))