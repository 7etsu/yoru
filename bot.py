import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

TOKEN = os.getenv("TOKEN")
RADIO_URL = "https://stream.zeno.fm/x9ko0jn9mzauv"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FFMPEG_OPTIONS = {
    "before_options": (
        "-nostdin "
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_on_network_error 1 "
        "-reconnect_on_http_error 4xx,5xx "
        "-reconnect_delay_max 5"
    ),
    "options": "-vn"
}

# --- SISTEMA PARA MANTER O RENDER ACORDADO ---
app = Flask('')

@app.route('/')
def home():
    return "Bot Online 24/7!"

def run_web():
    # O Render exige que o Web Service escute na porta fornecida pela variável PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def manter_vivo():
    t = Thread(target=run_web)
    t.start()
# ---------------------------------------------

def tocar_radio(voice):
    if voice.is_playing():
        try: voice.stop()
        except: pass

    source = discord.FFmpegPCMAudio(RADIO_URL, executable="ffmpeg", **FFMPEG_OPTIONS)

    def after_play(error):
        if error: print(f"Aviso FFmpeg: {error}")
        if voice.is_connected():
            bot.loop.create_task(reconectar(voice))

    voice.play(source, after=after_play)

async def reconectar(voice):
    await asyncio.sleep(3)
    if voice.is_connected():
        tocar_radio(voice)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado no Render como {bot.user}")

@bot.command()
async def radio(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ Você precisa estar em um canal de voz.")
        return
    canal = ctx.author.voice.channel
    voice = ctx.voice_client if ctx.voice_client else await canal.connect()
    if voice.channel != canal: await voice.move_to(canal)
    tocar_radio(voice)
    await ctx.send("📻 Rádio iniciada no Render!")

@bot.command()
async def parar(ctx):
    if ctx.voice_client:
        voice = ctx.voice_client
        if voice.is_playing():
            try: voice.stop()
            except: pass
        await voice.disconnect()
        await ctx.send("🛑 Rádio parada.")

# Inicia o servidor web antes de ligar o bot
manter_vivo()
bot.run(TOKEN)
