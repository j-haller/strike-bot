import discord
import datetime as dt
from discord.ext import commands
from bot.db import get_db

DEFAULT_STRIKES = 1
MAX_STRIKES = 5
POLL_ANSWER_YES = "Yes"
POLL_ANSWER_NO = "No"
POLL_DURATION_HOURS = 1
POLL_TYPE_ADD = 'add'
POLL_TYPE_HONOR = 'honor'
POLL_STATUS_PENDING = 'pending'
POLL_STATUS_ACCEPTED = 'accepted'
POLL_STATUS_REJECTED = 'rejected'
USER_DELETED_NO = 'no'

class Strike(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # add member to the database
    @discord.app_commands.command(name="addmember", description="Add a member")
    async def addmember(self, interaction: discord.Interaction, member: discord.Member):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)

        # check if member is already in database
        if await self.getUserId(memberId, guildId):
            await interaction.response.send_message(f"{memberName} already exists.")

        else:
            await self.insertData("user", ["member_id", "guild_id"], [memberId, guildId])
            await interaction.response.send_message(f"{memberName} has been added.")


    # add strike to a member using poll
    @discord.app_commands.command(name="addstrike", description="Start poll to vote on strike(s)")
    async def addstrike(self, interaction: discord.Interaction, member: discord.Member, strikes: int = DEFAULT_STRIKES):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)

        if strikes > MAX_STRIKES:
            await interaction.response.send_message(f"{MAX_STRIKES} is the maximum number of strikes.")
            return

        userId = await self.getUserId(memberId, guildId)

        # member does not exist
        if not userId:
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        # create poll
        poll = discord.Poll(
            question=f"Should {memberName} receive {strikes} strike(s)?",
            duration=dt.timedelta(hours=POLL_DURATION_HOURS)
        )
        poll.add_answer(text=POLL_ANSWER_YES)
        poll.add_answer(text=POLL_ANSWER_NO)


        await interaction.response.send_message(poll=poll)
        message = await interaction.original_response()
        messageId = message.id

        # create poll record
        await self.insertData("poll",
                              ["poll_type", "user_id", "strikes", "message_id", "guild_id"],
                              [POLL_TYPE_ADD, userId, strikes, messageId, guildId])


    # honor strike of a member using poll
    @discord.app_commands.command(name="honorstrike", description="Start poll to vote on honored strike(s)")
    async def honorstrike(self, interaction: discord.Interaction, member: discord.Member, strikes: int = DEFAULT_STRIKES):
        memberId = str(member.id)
        guildId = str(interaction.guild_id)
        memberName = str(member.display_name)

        if strikes > MAX_STRIKES:
            await interaction.response.send_message(f"{MAX_STRIKES} is the maximum number of honored strikes.")
            return

        userId = await self.getUserId(memberId, guildId)

        # member does not exist
        if not userId:
            await interaction.response.send_message(f"{memberName} must be added first.")
            return

        # create poll
        poll = discord.Poll(
            question=f"Has {memberName} honored {strikes} strike(s)?",
            duration=dt.timedelta(hours=POLL_DURATION_HOURS)
        )
        poll.add_answer(text=POLL_ANSWER_YES)
        poll.add_answer(text=POLL_ANSWER_NO)


        await interaction.response.send_message(poll=poll)
        message = await interaction.original_response()
        messageId = message.id

        # create poll record
        await self.insertData("poll",
                              ["poll_type", "user_id", "strikes", "message_id", "guild_id"],
                              [POLL_TYPE_HONOR, userId, strikes, messageId, guildId])


    # listen for votes
    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent):
        memberId = str(payload.user_id)
        guildId = str(payload.guild_id)

        # ignore votes from non-members
        if not await self.getUserId(memberId, guildId):
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        messageId = message.id
        poll = message.poll

        memberTotal = await self.getMemberTotal()

        # count member votes per answer and check if majority is irreversible
        for pollAnswer in poll.answers:
            memberVotes = 0
            async for voter in pollAnswer.voters():
                if await self.getUserId(memberId, guildId):
                    memberVotes += 1

            # poll result is irreversible
            if memberVotes > memberTotal / 2:
                await poll.end()

                status = POLL_STATUS_ACCEPTED if pollAnswer.text == POLL_ANSWER_YES else POLL_STATUS_REJECTED
                row = await self.getPoll(messageId, guildId)

                # poll not in database (should not happen)
                if not row:
                    await interaction.response.send_message("Poll not found")
                    return

                pollId, pollType, userId, strikes = row

                await self.updatePoll(pollId, status)

                # poll rejected: do nothing
                if status == POLL_STATUS_REJECTED:
                    return

                if pollType == POLL_TYPE_ADD:

                    # create strike(s)
                    await self.insertData("strike",
                                        ["user_id", "poll_id_created"],
                                        [userId, pollId],
                                          strikes)

                    # honor strike(s)
                elif pollType == POLL_TYPE_HONOR:
                    await self.honorStrike(pollId, userId, strikes)

                return


    # show help
    @discord.app_commands.command(name="help", description="Show available commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Strike Bot Commands")
        embed.add_field(name="/adduser <member>", value="Add a member to the bot.", inline=False)
        embed.add_field(name="/addstrike <member> [strikes]", value=f"Start a {POLL_DURATION_HOURS}-hour poll to give a member one or more strikes. Defaults to {DEFAULT_STRIKES}, maximum is {MAX_STRIKES}.", inline=False)
        embed.add_field(name="/honorstrike <member> [strikes]", value=f"Start a {POLL_DURATION_HOURS}-hour poll to honor one or more strikes of a member. Defaults to {DEFAULT_STRIKES}, maximum is {MAX_STRIKES}.", inline=False)
        embed.add_field(name="/showstrikes [member]", value="Show accepted strikes for a member, or all members if none specified.", inline=False)
        embed.add_field(name="/help", value="Show this help message.", inline=False)
        await interaction.response.send_message(embed=embed)


    # show strikes of member or all members
    @discord.app_commands.command(name="showstrikes", description="Show strikes of a member, or all members if none specified")
    async def showstrikes(self, interaction: discord.Interaction, member: discord.Member | None = None):
        guildId = str(interaction.guild_id)

        if member is not None:
            memberId = str(member.id)
            memberName = str(member.display_name)

            userId = await self.getUserId(memberId, guildId)
            if not userId:
                await interaction.response.send_message(f"{memberName} must be added first.")
                return

            strikes = await self.getStrikes(userId)
            await interaction.response.send_message(f"{memberName} has {strikes} strike(s).")

        else:
            rows = await self.getAllStrikes(guildId)
            if not rows:
                await interaction.response.send_message("No members registered.")
                return

            embed = discord.Embed(title="Strikes")
            for memberId, strikes in rows:
                discordMember = interaction.guild.get_member(int(memberId))
                name = discordMember.display_name if discordMember else f"Unknown ({memberId})"
                embed.add_field(name=name, value=f"{strikes} strike(s)", inline=False)
            await interaction.response.send_message(embed=embed)


    # get user id
    async def getUserId(self, memberId, guildId):
        async with get_db() as db:
            async with db.execute(
                """SELECT u.id
                   FROM user u
                   WHERE u.member_id = ?
                   AND u.guild_id = ?
                   AND u.deleted = ?""",
                [memberId, guildId, USER_DELETED_NO]
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else None


    # get poll
    async def getPoll(self, messageId, guildId):
        async with get_db() as db:
            async with db.execute(
                """SELECT p.id, p.poll_type, p.user_id, p.strikes
                   FROM poll p
                   WHERE p.message_id = ?
                   AND p.guild_id = ?
                   AND p.status = ?""",
                [messageId, guildId, POLL_STATUS_PENDING]
            ) as cursor:
                return await cursor.fetchone()


    # get strikes for user
    async def getStrikes(self, userId):
        async with get_db() as db:
            async with db.execute(
                """SELECT COUNT(s.id)
                   FROM strike s
                   WHERE s.user_id = ?
                   AND s.poll_id_honored IS NULL""",
                [userId]
            ) as cursor:
                row = await cursor.fetchone()

        return row[0]


    # insert data into database
    async def insertData(self, table, columns, values, repeat=1):
        cols = ', '.join(columns)
        placeholders = ', '.join(['?'] * len(values))

        async with get_db() as db:
            await db.executemany(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                [values] * repeat
            )
            await db.commit()


    # update poll
    async def updatePoll(self, pollId, status):
        async with get_db() as db:
            await db.execute(
                """UPDATE poll
                   SET status = ?
                   WHERE id = ?""",
                [pollId, status]
            )
            await db.commit()


    # honor strike
    async def honorStrike(self, pollId, userId, strikes):
        async with get_db() as db:
            await db.execute(
                """UPDATE strike
                   SET poll_id_honored = ?
                   WHERE user_id = ?
                   AND poll_id_honored IS NULL
                   ORDER BY id
                   LIMIT ?""",
                [pollId, userId, strikes]
            )
            await db.commit()


    # get all members with strike counts for a guild
    async def getAllStrikes(self, guildId):
        async with get_db() as db:
            async with db.execute(
                """SELECT u.member_id, COUNT(s.id)
                   FROM user u
                   LEFT JOIN strike s
                   ON s.user_id = u.id
                   AND s.poll_id_honored IS NULL
                   WHERE u.guild_id = ?
                   AND u.deleted = 'no'
                   GROUP BY u.id""",
                [guildId]
            ) as cursor:
                return await cursor.fetchall()


    # get member total from database
    async def getMemberTotal(self):
        async with get_db() as db:
            async with db.execute(
                """SELECT COUNT(u.id)
                    FROM user u
                    WHERE u.deleted = 'no'"""
            ) as cursor:
                row = await cursor.fetchone()

        return row[0]


async def setup(bot):
    await bot.add_cog(Strike(bot))
