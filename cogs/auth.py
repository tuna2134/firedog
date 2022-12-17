# Cog - auth
from discord.ext import commands
from discord import app_commands
import discord
from captcha.image import ImageCaptcha

from lib.guild_logger import GuildLogger

import random
import string


def random_str(length: int) -> str:
    return "".join(random.choices(string.digits, k=length))


class ImageModal(
    discord.ui.Modal, title="画像認証"
):
    user_answer = discord.ui.TextInput(label="認証コード")

    def __init__(self, answer: str):
        self.answer = answer
        super().__init__()
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.user_answer.value == self.answer:
            async with interaction.client.pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT * FROM Auth WHERE GuildId = %s",
                        (interaction.guild.id,)
                    )
                    _, role_id, _ = await cursor.fetchone()
                    role = interaction.guild.get_role(role_id) or \
                        await interaction.guild.fetch_role(role_id)
                    logger = GuildLogger(interaction.guild, interaction.client)
                    if role is not None:
                        try:
                            await interaction.user.add_roles(role)
                        except discord.Forbidden:
                            logger.error(
                                "画像認証",
                                "ロールの付与に失敗しました。\n"
                                "権限が足りない可能性があります。"
                            )
                    else:
                        logger.error(
                            "画像認証",
                            "認証に成功しましたが、ロールが見つかりませんでした。"
                        )
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="画像認証",
                    description="認証に成功しました。",
                    color=discord.Color.green()
                ), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="画像認証",
                    description="答えが間違っています。",
                    color=discord.Color.red()
                ), ephemeral=True
            )


class ImageUserView(discord.ui.View):
    answer: str | None = None

    def __init__(self, answer: str):
        super().__init__()
        self.answer = answer

    @discord.ui.button(label="答える")
    async def user_answer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ImageModal(self.answer))


class ImageView(discord.ui.View):
    def __init__(self):
        super().__init__(
            timeout=None
        )
        self.image = ImageCaptcha()
    
    @discord.ui.button(
        label="認証する", style=discord.ButtonStyle.green,
        custom_id="auth_image"
    )
    async def auth(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        answer = random_str(5)
        image = self.image.generate(answer)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="画像認証",
                description="画像の答えが分かり次第、下のボタンをクリックしてください。",
            ).set_image(url="attachment://image.png"), view=ImageUserView(answer),
            file=discord.File(image, "image.png"), ephemeral=True
        )


class Auth(commands.Cog):
    auth = app_commands.Group(
        name="auth",
        description="認証に関するコマンドです。",
        guild_only=True
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool = bot.pool
        self.image_view = ImageView()
        bot.add_view(self.image_view)

    async def cog_load(self) -> None:
        async with self.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "CREATE TABLE IF NOT EXISTS Auth (GuildId BIGINT, RoleId BIGINT, Mode TEXT);"
                )
    
    @auth.command(description="画像認証")
    @app_commands.describe(role="認証に成功したユーザーに付与するロール")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def image(self, interaction: discord.Interaction, role: discord.Role) -> None:
        async with self.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM Auth WHERE GuildId = %s", (interaction.guild.id,))
                if await cursor.fetchone():
                    await interaction.response.send_message(embed=discord.Embed(
                        title="エラー",
                        description="画像認証はすでに設定されています。"
                        "オフにするには`/auth off`を実行してください。",
                        color=discord.Color.red()
                    ))
                else:
                    await cursor.execute(
                        "INSERT INTO Auth VALUES (%s, %s, %s);",
                        (interaction.guild.id, role.id, "image")
                    )
                    await interaction.channel.send(
                        embed=discord.Embed(
                            title="画像認証",
                            description="認証するには下のボタンをクリックしてください。"
                        ), view=self.image_view
                    )
                    await interaction.response.send_message(embed=discord.Embed(
                        title="画像認証",
                        description="設定しました。",
                        color=discord.Color.green()
                    ), ephemeral=True)

    @auth.command(description="認証をオフにします。")
    async def off(self, interaction: discord.Interaction) -> None:
        async with self.pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM Auth WHERE GuildId = %s", (interaction.guild.id,))
                await interaction.response.send_message(embed=discord.Embed(
                    title="認証",
                    description="認証をオフにしました。",
                    color=discord.Color.green()
                ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Auth(bot))