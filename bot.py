import os
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import mlb_api
import storage

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
POLL_MINUTES = float(os.getenv("POLL_MINUTES", "1"))
LEAD_THRESHOLD = int(os.getenv("LEAD_THRESHOLD", "8"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("blowout_bot")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def et_date_str(offset_days: int = 0) -> str:
    et = datetime.now(timezone.utc) - timedelta(hours=4)
    et += timedelta(days=offset_days)
    return et.strftime("%Y-%m-%d")


def leading_side(game: dict):
    """Returns (leading_team, trailing_team, lead) or None if scores aren't in or tied."""
    home_runs, away_runs = game["home_runs"], game["away_runs"]
    if home_runs is None or away_runs is None:
        return None
    lead = abs(home_runs - away_runs)
    if lead == 0:
        return None
    if home_runs > away_runs:
        return game["home_team"], game["away_team"], lead
    return game["away_team"], game["home_team"], lead


def build_alert_embed(game: dict, leading_team: str, trailing_team: str, lead: int) -> discord.Embed:
    inning_state = game.get("inning_state") or ""
    inning = game.get("inning")
    inning_str = f"{inning_state} {inning}" if inning else "in progress"

    embed = discord.Embed(
        title=f"🚨 {leading_team} lead by {lead}",
        description=(
            f"**{game['away_team']}** {game['away_runs']} — "
            f"**{game['home_team']}** {game['home_runs']}\n"
            f"{inning_str}"
        ),
        color=discord.Color.red(),
    )
    embed.add_field(
        name="Why it matters",
        value=(
            f"{trailing_team} can now bring in a position player to pitch "
            f"(8+ run threshold reached). Bullpen usage/run-line implications kick in."
        ),
        inline=False,
    )
    embed.set_footer(text="Data: MLB Stats API")
    return embed


@tasks.loop(minutes=POLL_MINUTES)
async def poll_blowouts():
    channel_id = storage.get_config("announce_channel_id")
    if not channel_id:
        return

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        log.warning("Configured channel %s not found/visible to bot", channel_id)
        return

    date_str = et_date_str(0)
    try:
        games = mlb_api.get_live_games(date_str)
    except Exception as e:
        log.error("Failed to fetch live games: %s", e)
        return

    for g in games:
        if g["abstract_state"] != "Live":
            continue
        if storage.already_alerted(g["game_pk"]):
            continue

        result = leading_side(g)
        if not result:
            continue
        leading_team, trailing_team, lead = result

        if lead >= LEAD_THRESHOLD:
            storage.mark_alerted(g["game_pk"], date_str, leading_team, trailing_team, lead)
            try:
                await channel.send(embed=build_alert_embed(g, leading_team, trailing_team, lead))
                log.info("Alerted blowout: game %s, %s up %d", g["game_pk"], leading_team, lead)
            except Exception as e:
                log.error("Failed to send blowout alert for game %s: %s", g["game_pk"], e)


@poll_blowouts.before_loop
async def before_poll():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    storage.init_db()
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except Exception as e:
        log.error("Slash command sync failed: %s", e)
    if not poll_blowouts.is_running():
        poll_blowouts.start()
    log.info("Logged in as %s", bot.user)


@bot.tree.command(name="setchannel", description="Set this channel to receive blowout alerts")
@app_commands.checks.has_permissions(manage_guild=True)
async def setchannel(interaction: discord.Interaction):
    storage.set_config("announce_channel_id", str(interaction.channel_id))
    await interaction.response.send_message(
        f"✅ Blowout alerts (lead ≥ {LEAD_THRESHOLD} runs) will post in {interaction.channel.mention}."
    )


@bot.tree.command(name="blowouts", description="Check right now for any games currently up by 8+ runs")
async def blowouts(interaction: discord.Interaction):
    await interaction.response.defer()
    date_str = et_date_str(0)
    try:
        games = mlb_api.get_live_games(date_str)
    except Exception as e:
        await interaction.followup.send(f"Couldn't reach the MLB API right now: {e}")
        return

    hits = []
    for g in games:
        if g["abstract_state"] != "Live":
            continue
        result = leading_side(g)
        if result and result[2] >= LEAD_THRESHOLD:
            hits.append((g, *result))

    if not hits:
        await interaction.followup.send(f"No live games currently up by {LEAD_THRESHOLD}+ runs.")
        return

    embed = discord.Embed(title=f"Live games up by {LEAD_THRESHOLD}+ runs", color=discord.Color.orange())
    for g, leading_team, trailing_team, lead in hits:
        embed.add_field(
            name=f"{g['away_team']} @ {g['home_team']}",
            value=f"{g['away_runs']}-{g['home_runs']} — {leading_team} +{lead}",
            inline=False,
        )
    await interaction.followup.send(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in your .env file (see .env.example).")
    bot.run(TOKEN)
