import discord
from discord.ext import commands, tasks
import sqlite3
import asyncio
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

my_secret = os.getenv('TOKEN')
email_user = os.getenv('EMAIL_USER')
email_password = os.getenv('EMAIL_PASSWORD')

if not my_secret:
    print("Bot token not found in environment variables.")
    exit()

# Define the bot's intents
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Enable message content intent

# Create an instance of a bot
bot = commands.Bot(command_prefix='!', intents=intents)

# The ID of the channel where verification should happen
VERIFY_CHANNEL_ID = 1260919461431742484  

# Dictionary to store OTPs temporarily
otp_store = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    cleanup_otps.start()  # Start the cleanup task

@bot.command()
async def verify(ctx):
    if ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.reply('This command can only be used in the designated verification channel.')
        return

    print("Verification command received.")
    await ctx.reply('Please enter your application number:')
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        application_number_msg = await bot.wait_for('message', check=check, timeout=60.0)
        application_number = application_number_msg.content
        print(f'Application number received: {application_number}')

        with sqlite3.connect('database3.db') as conn:
            c = conn.cursor()
            # Check if user exists in the database and if details have been used
            c.execute("SELECT id, application_number, email, used FROM users WHERE application_number=?", (application_number,))
            result = c.fetchone()
            print(f'Database result: {result}')

        if result is None:
            await application_number_msg.reply('Verification failed. No matching record found.')
            print('Verification failed: No matching record found.')
        elif len(result) != 4:
            await application_number_msg.reply('Unexpected database result format.')
            print(f'Unexpected database result format: {result}')
        elif result[3]:  # Assuming 'used' is the 4th column in the result
            await application_number_msg.reply('Verification failed. These details have already been used.')
            print('Verification failed: Details already used.')
        else:
            email = result[2]
            otp = random.randint(100000, 999999)
            
            # Send OTP to user's email
            await send_otp_email(email, otp)
            await application_number_msg.reply('An OTP has been sent to your registered email. Please enter the OTP to complete verification:')

            otp_store[ctx.author.id] = otp  # Store OTP in memory

            otp_msg = await bot.wait_for('message', check=check, timeout=300.0)
            entered_otp = otp_msg.content
            print(f'OTP received: {entered_otp}')

            original_otp = otp_store.get(ctx.author.id)

            if entered_otp == str(original_otp):
                role = discord.utils.get(ctx.guild.roles, name='Freshers')
                if role:
                    try:
                        # Assign the role to the user
                        await ctx.author.add_roles(role)
                        
                        # Mark the details as used
                        with sqlite3.connect('database3.db') as conn:
                            c = conn.cursor()
                            c.execute("UPDATE users SET used=1 WHERE id=?", (result[0],))
                            conn.commit()
                        
                        await otp_msg.reply(f'Verified. Role {role.name} has been assigned.')
                        print(f'Role {role.name} assigned to {ctx.author}')
                        del otp_store[ctx.author.id]  # Remove OTP after successful verification
                    except discord.Forbidden:
                        await otp_msg.reply('I do not have permission to assign roles.')
                        print('Permission error: Cannot assign role.')
                    except discord.HTTPException as e:
                        await otp_msg.reply('An error occurred while assigning the role.')
                        print(f'HTTP error: {e}')
                else:
                    await otp_msg.reply('Role not found.')
                    print('Role not found.')
            else:
                await otp_msg.reply('Verification failed. Incorrect or expired OTP.')
                print('Verification failed: Incorrect or expired OTP.')

    except asyncio.TimeoutError:
        await ctx.reply('You took too long to respond. Please try again.')
        print('Timeout error.')
    except Exception as e:
        await ctx.reply('An unexpected error occurred. Please try again later.')
        print(f'Unexpected error: {e}')

async def send_otp_email(email, otp):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = email
        msg['Subject'] = 'Discord FROSH 24 verification mail'

        body = f'Your OTP is {otp}. Please use this to complete your verification.'
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_password)
        text = msg.as_string()
        server.sendmail(email_user, email, text)
        server.quit()
        print(f'OTP sent to {email}')
    except Exception as e:
        print(f'Failed to send OTP email: {e}')

@tasks.loop(minutes=5)  # Run this task every 5 minutes
async def cleanup_otps():
    for user_id in list(otp_store.keys()):
        try:
            del otp_store[user_id]
            print(f'Expired OTP deleted for user ID: {user_id}')
        except Exception as e:
            print(f'Error during OTP cleanup: {e}')

# Run the bot
try:
    bot.run(my_secret)
except discord.LoginFailure as e:
    print(f'Failed to login: {e}')
