import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# LangChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv("safe.env")

# 1. Setup Discord Bot (With Intents to read messages)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 2. Setup Gemini Engine
llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview", 
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.7
)

@bot.event
async def on_ready():
    print(f'[SUCCESS] {bot.user} has successfully connected to Discord!')

# --- BOT COMMANDS ---

@bot.command(name='helper')
async def general_helper(ctx, *, user_input: str):
    """General AI assistant. Usage: !helper <your question>"""
    # Send a temporary loading message
    loading_msg = await ctx.send("🤖 *Thinking...*")
    
    try:
        messages = [
            SystemMessage(content="You are Omni-Helper, a professional assistant. Keep answers clear and use Markdown."),
            HumanMessage(content=user_input)
        ]
        response = llm.invoke(messages)
        
        # Extract text no matter how LangChain formats it
        ai_output = response.content
        if isinstance(ai_output, list):
            clean_text = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item) 
                for item in ai_output
            )
        else:
            clean_text = str(ai_output)
            
        # Discord has a 2000 character limit per message
        final_text = clean_text[:1990]
        await loading_msg.edit(content=final_text)
        
    except Exception as e:
        await loading_msg.edit(content=f"❌ Error: {str(e)}")

@bot.command(name='legal')
async def legal_auditor(ctx, *, user_input: str):
    """T&C Explainer. Usage: !legal <text>"""
    loading_msg = await ctx.send("⚖️ *Reading Terms & Conditions...*")
    
    try:
        messages = [
            SystemMessage(content="You are a Terms and Conditions Explainer. Summarize the text clearly. Keep it brief. Do not provide legal advice."),
            HumanMessage(content=user_input)
        ]
        response = llm.invoke(messages)
        
        # Extract text no matter how LangChain formats it
        ai_output = response.content
        if isinstance(ai_output, list):
            clean_text = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item) 
                for item in ai_output
            )
        else:
            clean_text = str(ai_output)
            
        await loading_msg.edit(content=clean_text[:1990])
        
    except Exception as e:
        await loading_msg.edit(content=f"❌ Error: {str(e)}")

# 3. Wake up the bot!
bot.run(os.getenv("DISCORD_BOT_TOKEN"))