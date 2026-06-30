import os
import asyncio
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from groq import Groq

load_dotenv()

TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RADIO_URL = "https://stream.zeno.fm/x9ko0jn9mzauv"

# Inicializa o cliente do Groq
groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CONFIGURAÇÃO DO BANCO DE DADOS (SQLite) ---
def iniciar_banco():
    conn = sqlite3.connect("rpg_isekai.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jogadores (
            user_id TEXT PRIMARY KEY,
            nome TEXT,
            classe TEXT,
            level INTEGER DEFAULT 1,
            hp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,
            gold INTEGER DEFAULT 0,
            historia TEXT
        )
    """)
    conn.commit()
    conn.close()

iniciar_banco()

def obter_jogador(user_id):
    conn = sqlite3.connect("rpg_isekai.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jogadores WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "nome": row[1], "classe": row[2],
            "level": row[3], "hp": row[4], "max_hp": row[5],
            "gold": row[6], "historia": row[7]
        }
    return None

def salvar_jogador(user_id, nome, classe, level, hp, max_hp, gold, historia):
    conn = sqlite3.connect("rpg_isekai.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO jogadores (user_id, nome, classe, level, hp, max_hp, gold, historia)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(user_id), nome, classe, level, hp, max_hp, gold, historia))
    conn.commit()
    conn.close()

# --- SISTEMA WEB (RENDER) ---
app = Flask('')
@app.route('/')
def home(): return "Bot RPG & Radio Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web).start()

# --- CONFIGURAÇÃO DE ÁUDIO ---
FFMPEG_OPTIONS = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5",
    "options": "-vn"
}

def tocar_radio(voice):
    if voice.is_playing():
        try: voice.stop()
        except: pass
    source = discord.FFmpegPCMAudio(RADIO_URL, executable="ffmpeg", **FFMPEG_OPTIONS)
    voice.play(source, after=lambda e: bot.loop.create_task(reconectar(voice)) if voice.is_connected() else None)

async def reconectar(voice):
    await asyncio.sleep(3)
    if voice.is_connected(): tocar_radio(voice)

# --- COMANDOS DO RPG ---

PROMPT_SISTEMA = (
    "Você é o Mestre Supremo de um RPG de texto estilo Isekai Sombrio. "
    "O jogador reencarnou em um mundo perigoso. Seja imersivo, descritivo e use humor ácido ou tom épico. "
    "Mantenha as respostas curtas (máximo 3 parágrafos) para caber no Discord. "
    "Sempre termine a narração dando 3 opções claras de escolha para o jogador (A, B, C) ou deixe em aberto para ele agir."
)

@bot.command()
async def comecar(ctx, nome: str, classe: str):
    """Cria a ficha do jogador e inicia a história na floresta"""
    user_id = ctx.author.id
    jogador = obter_jogador(user_id)
    
    if jogador:
        await ctx.send("⚠️ Você já tem uma jornada em andamento! Use `!jogar <sua ação>` para continuar.")
        return

    classes_validas = ["guerreiro", "mago", "ladino", "clérigo"]
    if classe.lower() not in classes_validas:
        await ctx.send(f"❌ Classe inválida! Escolha entre: {', '.join(classes_validas)}")
        return

    # Prompt inicial: Acordando na floresta sem nada
    introducao = (
        f"O jogador {nome} acabou de reencarnar como um {classe}. "
        "Ele abre os olhos e se vê caído no chão úmido de uma floresta densa e escura, cercada por barulhos sinistros. "
        "Ele está sem nada, vestindo apenas trapos velhos. Narre o despertar e dê as primeiras opções de sobrevivência."
    )

    await ctx.send("🌀 *A realidade se distorce... Você fecha os olhos em seu mundo antigo e acorda...*")
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": introducao}
            ],
            temperature=0.7,
        )
        resposta_ia = completion.choices[0].message.content
        
        # Salva o progresso inicial no banco de dados
        salvar_jogador(user_id, nome, classe.capitalize(), 1, 100, 100, 0, resposta_ia)
        
        embed = discord.Embed(title=f"🌲 Jornada Isekai Começou - {nome} o {classe.capitalize()}", description=resposta_ia, color=0x2ecc71)
        embed.set_footer(text="Use !jogar <sua ação ou escolha> para responder ao mestre.")
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Erro ao invocar o Mestre da IA: {e}")

@bot.command()
async def jogar(ctx, *, acao: str):
    """Envia a ação do jogador para a IA e atualiza o histórico"""
    user_id = ctx.author.id
    jogador = obter_jogador(user_id)

    if not jogador:
        await ctx.send("❌ Você ainda não começou sua jornada! Use: `!comecar <Nome> <Classe>`")
        return

    await ctx.typing()

    # Contexto completo enviado para o Groq lembrar de quem é o jogador e o que aconteceu antes
    contexto_rpg = (
        f"Histórico anterior da história: {jogador['historia']}\n\n"
        f"Status do Jogador: Nome: {jogador['nome']}, Classe: {jogador['classe']}, Level: {jogador['level']}, HP: {jogador['hp']}/{jogador['max_hp']}, Gold: {jogador['gold']}.\n"
        f"O jogador decidiu fazer a seguinte ação: '{acao}'.\n"
        "Com base na ação dele, continue a história. Se a ação foi perigosa, narre se ele teve sucesso ou falhou. "
        "Se ele encontrou tesouros ou derrotou monstros fracos, você pode narrar que ele ganhou um pouco de Gold (avise no texto). "
        "Sempre dê novas opções no final."
    )

    try:
        completion = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": contexto_rpg}
            ],
            temperature=0.7,
        )
        nova_resposta = completion.choices[0].message.content
        
        # Aqui você pode expandir a lógica para alterar Gold ou HP baseado em respostas futuras da IA.
        # Por enquanto, mantemos o histórico atualizado.
        salvar_jogador(user_id, jogador['nome'], jogador['classe'], jogador['level'], jogador['hp'], jogador['max_hp'], jogador['gold'], nova_resposta)
        
        embed = discord.Embed(title=f"🎲 Turno de {jogador['nome']}", description=nova_resposta, color=0x3498db)
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Ocorreu um erro na narração: {e}")

@bot.command()
async def status(ctx):
    """Mostra a ficha atual do jogador"""
    jogador = obter_jogador(ctx.author.id)
    if not jogador:
        await ctx.send("❌ Você não possui um personagem criado. Use `!comecar`.")
        return

    embed = discord.Embed(title=f"📜 Ficha de Personagem: {jogador['nome']}", color=0xe67e22)
    embed.add_field(name="Classe", value=jogador['classe'], inline=True)
    embed.add_field(name="Nível", value=f"⭐ {jogador['level']}", inline=True)
    embed.add_field(name="Vida (HP)", value=f"❤️ {jogador['hp']}/{jogador['max_hp']}", inline=True)
    embed.add_field(name="Moedas de Ouro", value=f"💰 {jogador['gold']}g", inline=True)
    await ctx.send(embed=embed)

# --- COMANDOS DA RÁDIO ---
@bot.command()
async def radio(ctx):
    if not ctx.author.voice: return await ctx.send("❌ Você precisa estar em um canal de voz.")
    voice = ctx.voice_client if ctx.voice_client else await ctx.author.voice.channel.connect()
    tocar_radio(voice)
    await ctx.send("📻 Rádio iniciada de fundo para o RPG!")

@bot.command()
async def parar(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Rádio parada.")

bot.run(TOKEN)
