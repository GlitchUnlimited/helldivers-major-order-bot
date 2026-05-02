import discord
from discord.ext import commands, tasks
import aiohttp
import os
import json
from datetime import timedelta
import asyncio

intents = discord.Intents.default()
intents.message_content = False  # We don't need it

bot = commands.Bot(command_prefix="!", intents=intents)

# === CONFIG ===
MAJOR_ORDERS_CHANNEL_ID = 123456789012345678  # ← CHANGE THIS to your channel ID (right-click channel → Copy ID)
STATE_FILE = "last_major_order.json"
API_MAJOR_ORDERS = "https://helldiverstrainingmanual.com/api/v1/war/major-orders"

# Load last known major order
def load_last_order():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f).get("last_id32")
    return None

def save_last_order(order_id):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_id32": order_id}, f)

async def fetch_major_orders():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_MAJOR_ORDERS) as resp:
            if resp.status != 200:
                print("API error:", resp.status)
                return None
            return await resp.json()

def format_time_left(seconds: int):
    if seconds <= 0:
        return "Expired"
    td = timedelta(seconds=seconds)
    days = td.days
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and watching for Major Orders!")
    check_major_orders.start()

@tasks.loop(minutes=5)  # Checks every 5 minutes
async def check_major_orders():
    data = await fetch_major_orders()
    if not data or len(data) == 0:
        return

    order = data[0]  # Usually only one active Major Order
    order_id = order.get("id32")
    last_id = load_last_order()

    if order_id != last_id and order_id is not None:
        # NEW MAJOR ORDER DETECTED!
        save_last_order(order_id)
        await post_major_order(order, is_new=True)

async def post_major_order(order, is_new=False):
    channel = bot.get_channel(MAJOR_ORDERS_CHANNEL_ID)
    if not channel:
        print("Channel not found! Check MAJOR_ORDERS_CHANNEL_ID")
        return

    setting = order.get("setting", {})
    title = setting.get("overrideTitle", "MAJOR ORDER")
    brief = setting.get("overrideBrief", "No briefing available.")
    expires_in = order.get("expiresIn", 0)
    progress = order.get("progress", [])

    # Nice embed
    embed = discord.Embed(
        title=f"🪖 {title}",
        description=brief,
        color=0xFF0000  # Super Earth red
    )
    embed.add_field(name="⏳ Time Remaining", value=format_time_left(expires_in), inline=True)
    embed.add_field(name="📊 Progress", value=str(progress), inline=True)
    
    if setting.get("rewards"):
        reward_text = "\n".join([f"• {r.get('amount', 0)} Medals" for r in setting["rewards"]])
        embed.add_field(name="🎖️ Rewards", value=reward_text or "Unknown", inline=False)

    embed.set_footer(text="High Command • Live from the frontlines")
    embed.timestamp = discord.utils.utcnow()

    # Create a thread for this Major Order
    message = await channel.send(embed=embed)
    thread = await message.create_thread(
        name=f"🪖 Major Order: {title}",
        auto_archive_duration=4320  # 3 days
    )

    if is_new:
        await thread.send("**🚨 NEW MAJOR ORDER ISSUED!** Democracy calls! Spread the word and get to the frontlines, Helldivers! 🪖")

    print(f"Posted new Major Order: {title}")

@bot.tree.command(name="major_order", description="Post the current Major Order in a new thread")
async def manual_major_order(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_major_orders()
    if data and len(data) > 0:
        await post_major_order(data[0])
        await interaction.followup.send("✅ Current Major Order posted in a thread!", ephemeral=True)
    else:
        await interaction.followup.send("No active Major Order right now.", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
